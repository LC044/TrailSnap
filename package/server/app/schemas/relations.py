from typing import Literal

from pydantic import BaseModel

RelationType = Literal["person", "place", "memory", "photo"]


class RelationTarget(BaseModel):
    kind: RelationType
    id: str | None = None
    name: str | None = None
    level: str | None = None
    place_key: str | None = None
    sceneId: str | None = None


class RelationNode(BaseModel):
    id: str
    type: RelationType
    label: str
    subtitle: str
    photo_id: str | None = None
    detail_target: RelationTarget | None = None


class RelationEdge(BaseModel):
    source: str
    target: str
    memory_count: int
    photo_count: int
    relation_kinds: list[str]
    evidence_summary: str


class NeighborPage(BaseModel):
    center: RelationNode
    nodes: list[RelationNode]
    edges: list[RelationEdge]
    has_more: bool
    next_cursor: str | None = None


class NodePage(BaseModel):
    items: list[RelationNode]
    has_more: bool
    next_cursor: str | None = None


class EvidencePage(NodePage):
    objects: list[RelationNode]
