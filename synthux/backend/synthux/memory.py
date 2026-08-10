"""Limited working memory for synthetic users.

Real users forget. An unconstrained LLM remembers every label it saw over a
15-minute journey, which makes it superhuman and corrupts usability results.
Each participant carries a salience-weighted buffer: observations decay every
step, and only the top-k survive into the next step's prompt context.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MemoryItem:
    content: str                 # e.g. "Billing screen had a 'Manage mandate' link"
    salience: float              # task relevance x visual prominence at encoding
    step_seen: int


@dataclass
class WorkingMemory:
    capacity: int                # persona.memory.working_memory_items
    decay_per_step: float = 0.15  # persona.memory.decay_per_step
    items: list[MemoryItem] = field(default_factory=list)

    def observe(self, content: str, salience: float, step: int) -> None:
        """Encode an observation; duplicates refresh instead of stacking."""
        for item in self.items:
            if item.content == content:
                item.salience = max(item.salience, salience)
                item.step_seen = step
                return
        self.items.append(MemoryItem(content=content, salience=salience, step_seen=step))
        self._evict()

    def tick(self) -> None:
        """Apply per-step decay, then drop anything effectively forgotten."""
        for item in self.items:
            item.salience *= (1.0 - self.decay_per_step)
        self.items = [i for i in self.items if i.salience >= 0.05]
        self._evict()

    def recall(self) -> list[str]:
        """What survives into the next prompt, most salient first."""
        return [i.content for i in sorted(self.items, key=lambda i: -i.salience)]

    def _evict(self) -> None:
        if len(self.items) > self.capacity:
            self.items = sorted(self.items, key=lambda i: -i.salience)[: self.capacity]
