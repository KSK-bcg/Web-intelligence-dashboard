import uuid
from uuid import uuid4
from datetime import datetime
from typing import Optional, List
from sqlmodel import SQLModel, Field, Session, create_engine, select


class RunRecord(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], primary_key=True)
    goal: str
    target: str
    status: str = "running"  # running | complete | failed
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


class PersonRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="runrecord.id")
    linkedin_id: str
    name: str
    title: str
    department: Optional[str] = None
    confidence: str = "medium"  # high | medium | low
    reports_to_linkedin_id: Optional[str] = None


class ChangeEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str
    person_name: str
    linkedin_id: str
    change_type: str  # promotion | new_hire | departure | title_change
    from_value: Optional[str] = None
    to_value: Optional[str] = None
    detected_at: datetime = Field(default_factory=datetime.utcnow)


class FinancialRecord(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4())[:8], primary_key=True)
    run_id: str = Field(index=True)
    company: str
    period: str
    revenue_usd_millions: Optional[float] = None
    revenue_yoy_growth_pct: Optional[float] = None
    gross_margin_pct: Optional[float] = None
    operating_margin_pct: Optional[float] = None
    net_margin_pct: Optional[float] = None
    ebitda_usd_millions: Optional[float] = None
    rd_spend_pct_revenue: Optional[float] = None
    capex_pct_revenue: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Store:
    def __init__(self, db_path: str = "intelligence.db"):
        self.engine = create_engine(f"sqlite:///{db_path}")

    def init_db(self):
        SQLModel.metadata.create_all(self.engine)

    def create_run(self, goal: str, target: str) -> str:
        run = RunRecord(goal=goal, target=target)
        with Session(self.engine) as session:
            session.add(run)
            session.commit()
            return run.id

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        with Session(self.engine) as session:
            return session.get(RunRecord, run_id)

    def complete_run(self, run_id: str):
        with Session(self.engine) as session:
            run = session.get(RunRecord, run_id)
            if run:
                run.status = "complete"
                run.completed_at = datetime.utcnow()
                session.add(run)
                session.commit()

    def fail_run(self, run_id: str):
        with Session(self.engine) as session:
            run = session.get(RunRecord, run_id)
            if run:
                run.status = "failed"
                run.completed_at = datetime.utcnow()
                session.add(run)
                session.commit()

    def list_runs(self) -> List[RunRecord]:
        with Session(self.engine) as session:
            return list(session.exec(select(RunRecord).order_by(RunRecord.created_at.desc())))

    def save_financial(self, run_id: str, financial: dict) -> "FinancialRecord":
        metrics = financial.get("metrics", {})
        record = FinancialRecord(
            run_id=run_id,
            company=financial.get("company", ""),
            period=financial.get("period", ""),
            revenue_usd_millions=metrics.get("revenue_usd_millions"),
            revenue_yoy_growth_pct=metrics.get("revenue_yoy_growth_pct"),
            gross_margin_pct=metrics.get("gross_margin_pct"),
            operating_margin_pct=metrics.get("operating_margin_pct"),
            net_margin_pct=metrics.get("net_margin_pct"),
            ebitda_usd_millions=metrics.get("ebitda_usd_millions"),
            rd_spend_pct_revenue=metrics.get("rd_spend_pct_revenue"),
            capex_pct_revenue=metrics.get("capex_pct_revenue"),
        )
        with Session(self.engine) as session:
            session.add(record)
            session.commit()
            session.refresh(record)
        return record

    def list_financials(self, run_id: str) -> List["FinancialRecord"]:
        with Session(self.engine) as session:
            return list(session.exec(
                select(FinancialRecord).where(FinancialRecord.run_id == run_id)
            ))

    def save_person(self, run_id: str, person: dict) -> PersonRecord:
        record = PersonRecord(run_id=run_id, **person)
        with Session(self.engine) as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_people(self, run_id: str) -> List[PersonRecord]:
        with Session(self.engine) as session:
            return list(session.exec(select(PersonRecord).where(PersonRecord.run_id == run_id)))

    def get_latest_run_for_target(self, target: str, exclude_run_id: str) -> Optional[RunRecord]:
        with Session(self.engine) as session:
            stmt = (
                select(RunRecord)
                .where(RunRecord.target == target)
                .where(RunRecord.status == "complete")
                .where(RunRecord.id != exclude_run_id)
                .order_by(RunRecord.completed_at.desc())
            )
            return session.exec(stmt).first()

    def diff_runs(self, prior_run_id: str, current_run_id: str) -> List[ChangeEvent]:
        prior_people = {p.linkedin_id: p for p in self.get_people(prior_run_id)}
        current_people = {p.linkedin_id: p for p in self.get_people(current_run_id)}
        changes = []

        for lid, person in current_people.items():
            if lid not in prior_people:
                changes.append(ChangeEvent(
                    run_id=current_run_id,
                    person_name=person.name,
                    linkedin_id=lid,
                    change_type="new_hire",
                    to_value=person.title,
                ))
            elif prior_people[lid].title != person.title:
                changes.append(ChangeEvent(
                    run_id=current_run_id,
                    person_name=person.name,
                    linkedin_id=lid,
                    change_type="promotion",
                    from_value=prior_people[lid].title,
                    to_value=person.title,
                ))

        for lid, person in prior_people.items():
            if lid not in current_people:
                changes.append(ChangeEvent(
                    run_id=current_run_id,
                    person_name=person.name,
                    linkedin_id=lid,
                    change_type="departure",
                    from_value=person.title,
                ))

        return changes
