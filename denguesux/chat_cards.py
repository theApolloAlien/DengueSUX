"""Typed cards built only from tool results, never from generated prose."""
from typing import Literal
from pydantic import BaseModel, Field, TypeAdapter
from typing import Annotated, Union

class AreaCard(BaseModel):
    type: Literal['area'] = 'area'
    code: str
    name: str
    priority: str
    people: int
    clusters: int
    snapshot_date: str | None = None
    trend: str = '14-day trend unavailable'
    aedes_date: str | None = None

class TopRow(BaseModel):
    code: str
    name: str
    priority: str
    people: int
    clusters: int

class TopCard(BaseModel):
    type: Literal['top_areas'] = 'top_areas'
    rows: list[TopRow]

class ForecastCard(BaseModel):
    type: Literal['forecast'] = 'forecast'
    prediction: float
    lower: float | None = None
    upper: float | None = None
    target_date: str
    segment: str
    series: list[float] = Field(default_factory=list)

class PlanCard(BaseModel):
    type: Literal['plan'] = 'plan'
    code: str
    name: str
    stops: int
    distance_km: float | None = None
    route: dict | None = None

class NoticeCard(BaseModel):
    type: Literal['notice'] = 'notice'
    code: str
    name: str
    language: str
    text: str
    label: str = 'Draft: review before sending'

Card = Annotated[Union[AreaCard, TopCard, ForecastCard, PlanCard, NoticeCard], Field(discriminator='type')]
CARD_SCHEMA = TypeAdapter(list[Card])

def build_cards(calls, data):
    areas = data.get('current', {}).get('areas', [])
    by_name = {a['name']: a for a in areas}
    cards = []
    for call in calls:
        r, name = call['result'], call['tool']
        if r.get('error'):
            continue
        area = by_name.get(r.get('name') or r.get('area'))
        if name == 'get_area' and area:
            cards.append(AreaCard(code=area['code'], name=r['name'], priority=r['priority'], people=r['people_in_clusters'], clusters=r['cluster_count'], snapshot_date=r.get('snapshot_date'), aedes_date=(data.get('aedes', {}).get('area_dates') or {}).get(area['code'])))
        elif name == 'top_areas':
            cards.append(TopCard(rows=[TopRow(code=by_name[a['name']]['code'], name=a['name'], priority=a['priority'], people=a['people_in_clusters'], clusters=a['cluster_count']) for a in r['areas'] if a['name'] in by_name]))
        elif name == 'live_outlook':
            h = r['headline']
            cards.append(ForecastCard(prediction=h['prediction'], lower=h.get('lower'), upper=h.get('upper'), target_date=h['target_date'], segment='live', series=[x['prediction'] for x in r.get('forecasts', []) if isinstance(x.get('prediction'), (int,float))]))
        elif name == 'forecast_week':
            cards.append(ForecastCard(prediction=r['forecast_people'], target_date=r['target_week_start'], segment='2022 replay', series=[x['forecast_people'] for x in r.get('weeks_in_this_month', [])]))
        elif name == 'inspection_plan' and area:
            route = data.get('inspection', {}).get('areas', {}).get(area['code'], {}).get('route', {}).get('geometry')
            cards.append(PlanCard(code=area['code'], name=area['name'], stops=len(r['stops']), distance_km=r.get('walking_km'), route=route))
    return [c.model_dump() for c in cards]
