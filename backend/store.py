import math
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Column, Integer, String, Text, create_engine, delete, select, text
from sqlalchemy.orm import DeclarativeBase, Session

DIMENSIONS = 256


class Base(DeclarativeBase):
    pass


class Chunk(Base):
    __tablename__ = 'chunks'
    id = Column(String, primary_key=True)
    project = Column(String, index=True, nullable=False)
    path = Column(String, nullable=False)
    start = Column(Integer, nullable=False)
    end = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding_id = Column(String, nullable=False)
    embedding = Column(Vector(DIMENSIONS).with_variant(JSON(), 'sqlite'), nullable=False)


class Review(Base):
    __tablename__ = 'reviews'
    id = Column(String, primary_key=True)
    project = Column(String, index=True, nullable=False)
    created_at = Column(String, nullable=False)
    data = Column(JSON, nullable=False)


def chunk_file(path, content):
    lines = content.splitlines()
    for offset in range(0, len(lines), 36):
        yield {'id': str(uuid.uuid4()), 'path': path, 'start': offset + 1,
               'end': min(offset + 45, len(lines)), 'content': '\n'.join(lines[offset:offset + 45])}


def cosine(a, b):
    denominator = math.sqrt(sum(v * v for v in a) * sum(v * v for v in b))
    return sum(x * y for x, y in zip(a, b)) / denominator if denominator else 0.0


class Store:
    def __init__(self, url):
        self.engine = create_engine(url, connect_args={'check_same_thread': False} if url.startswith('sqlite') else {})
        if self.engine.dialect.name == 'postgresql':
            with self.engine.begin() as connection:
                connection.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
        Base.metadata.create_all(self.engine)

    def index(self, project, files, chunks, vectors, embedding_id):
        with Session(self.engine) as session, session.begin():
            session.execute(delete(Chunk).where(Chunk.project == project, Chunk.path.in_(files)))
            for chunk, vector in zip(chunks, vectors, strict=True):
                session.add(Chunk(**chunk, project=project, embedding=vector, embedding_id=embedding_id))

    def retrieve(self, project, vector, embedding_id, limit=5):
        with Session(self.engine) as session:
            query = select(Chunk).where(Chunk.project == project, Chunk.embedding_id == embedding_id)
            if self.engine.dialect.name == 'postgresql':
                chunks = session.scalars(query.order_by(Chunk.embedding.cosine_distance(vector)).limit(limit)).all()
            else:
                chunks = sorted(session.scalars(query).all(), key=lambda c: cosine(c.embedding, vector), reverse=True)[:limit]
            return [{'id': c.id, 'path': c.path, 'start': c.start, 'end': c.end,
                     'content': c.content, 'score': round(cosine(c.embedding, vector), 3)} for c in chunks]

    def inventory(self, project):
        with Session(self.engine) as session:
            chunks = session.scalars(select(Chunk).where(Chunk.project == project)).all()
            return {'project': project, 'files': sorted({c.path for c in chunks}), 'chunks': len(chunks)}

    def save_review(self, project, data):
        data = {**data, 'id': str(uuid.uuid4()), 'project': project,
                'created_at': datetime.now(timezone.utc).isoformat()}
        with Session(self.engine) as session, session.begin():
            session.add(Review(id=data['id'], project=project, created_at=data['created_at'], data=data))
        return data

    def list_reviews(self, project):
        with Session(self.engine) as session:
            rows = session.scalars(select(Review).where(Review.project == project).order_by(Review.created_at.desc()).limit(50)).all()
            return [{'id': r.id, 'title': r.data['title'], 'created_at': r.created_at,
                     'findings': len(r.data['findings']), 'provider': r.data['provider']} for r in rows]

    def get_review(self, review_id):
        with Session(self.engine) as session:
            row = session.get(Review, review_id)
            return row.data if row else None

    def feedback(self, review_id, finding_index, helpful):
        with Session(self.engine) as session, session.begin():
            row = session.scalar(select(Review).where(Review.id == review_id).with_for_update())
            if not row or finding_index < 0 or finding_index >= len(row.data['findings']):
                return None
            data = dict(row.data)
            findings = [dict(f) for f in data['findings']]
            findings[finding_index]['helpful'] = helpful
            row.data = {**data, 'findings': findings}
            return row.data
