from dataclasses import dataclass

@dataclass
class Score:
    name: str
    value: float
    notes: str

def pass_fail(scores: list[Score], threshold: float) -> bool:
    # Simple average threshold
    avg = sum(s.value for s in scores) / max(len(scores), 1)
    return avg >= threshold
