from pydantic import BaseModel


class Balance(BaseModel):
    holding: str  # currency id (e.g. amex_mr) or program id (e.g. united)
    points: int


class OptimizeRequest(BaseModel):
    balances: list[Balance] = []
    trip_ids: list[str] = []


class Allocation(BaseModel):
    trip_id: str
    trip_label: str
    method: str  # "points" | "cash"
    program: str | None = None  # program the award is booked in
    cabin: str
    sources: list[Balance] = []  # holdings the points come from (can pool several)
    points: int = 0
    cash_usd: float = 0  # fare paid in cash, or the award's taxes/fees
    fees_usd: float = 0
    value_usd: float = 0  # cash-equivalent value obtained with points
    cents_per_point: float | None = None
    reason: str


class StrategyResult(BaseModel):
    name: str
    allocations: list[Allocation]
    total_points: int
    total_value_usd: float
    cash_out_of_pocket_usd: float
    remaining_balances: list[Balance]


class SankeyNode(BaseModel):
    name: str


class SankeyLink(BaseModel):
    source: int
    target: int
    value: int


class OptimizeResponse(BaseModel):
    mock: bool
    greedy: StrategyResult
    portfolio: StrategyResult
    points_saved: int
    value_gained_usd: float
    sankey: dict[str, list]
