@dataclass
class _CommitChecks:
    thread: int
    callbacks: list
    checking: bool = False
    violated: bool = False
