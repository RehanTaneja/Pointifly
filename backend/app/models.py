from pydantic import BaseModel


class Balance(BaseModel):
    holding: str  # currency id (e.g. amex_mr) or program id (e.g. united)
    points: int


class CustomTrip(BaseModel):
    origin: str  # IATA code
    destination: str
    date: str  # YYYY-MM-DD, one-way
    cabin: str = "economy"
    label: str | None = None


class OptimizeRequest(BaseModel):
    balances: list[Balance] = []
    trip_ids: list[str] = []
    cabins: dict[str, str] = {}  # trip id -> cabin override
    custom_trips: list[CustomTrip] = []
    cards: list[str] | None = None  # the user's card product ids (from Plaid); None = default profile
    autopay: bool = True  # the user's choice: may the agent pay this plan's cash trips on its own


class Allocation(BaseModel):
    trip_id: str
    trip_label: str
    method: str  # "points" | "cash"
    program: str | None = None  # program the award is booked in
    cabin: str
    sources: list[Balance] = []  # holdings the points come from (can pool several)
    points: int = 0  # points moved out of the user's holdings (transfers go in fixed blocks)
    award_points: int = 0  # the award's price in the program's own points
    cash_usd: float = 0  # fare paid in cash, or the award's taxes/fees
    fees_usd: float = 0
    value_usd: float = 0  # cash-equivalent value obtained with points
    cents_per_point: float | None = None
    reason: str
    fare: dict | None = None  # live cash fare for this cabin: price, itinerary, google_flights_url
    award_source: dict | None = None  # where the points price came from: official chart or sample
    local_fx: dict | None = None  # Visa rate USD -> destination currency: {currency, rate, date, source}
    payment_card: dict | None = None  # Visa card that pays a cash leg and the points it earns


class StrategyResult(BaseModel):
    name: str
    allocations: list[Allocation]
    total_points: int
    total_value_usd: float
    cash_out_of_pocket_usd: float
    points_earned: int = 0  # earned paying cash legs with Visa cards
    remaining_balances: list[Balance]


class SankeyNode(BaseModel):
    name: str


class SankeyLink(BaseModel):
    source: int
    target: int
    value: int


class OptimizeResponse(BaseModel):
    mock: bool
    plan_id: str | None = None  # server-side record of the plan's cash legs (payments use it)
    skipped: list[str] = []  # trips left out because they couldn't be priced, with the reason
    greedy: StrategyResult
    portfolio: StrategyResult
    points_saved: int
    value_gained_usd: float
    sankey: dict[str, list]
