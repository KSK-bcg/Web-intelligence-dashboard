import pytest
from agent.store import Store


def test_save_and_retrieve_financial_record():
    store = Store(db_path=":memory:")
    store.init_db()
    run_id = store.create_run(goal="test", target="epic")

    store.save_financial(run_id=run_id, financial={
        "company": "Epic Systems",
        "period": "FY2023",
        "metrics": {
            "revenue_usd_millions": 4000.0,
            "revenue_yoy_growth_pct": 8.5,
            "gross_margin_pct": 72.0,
            "operating_margin_pct": 25.0,
            "net_margin_pct": 18.0,
            "ebitda_usd_millions": 1100.0,
            "rd_spend_pct_revenue": 15.0,
            "capex_pct_revenue": 4.0,
        },
        "key_risks": ["Competition from Oracle Health"],
        "confidence": "high",
    })

    records = store.list_financials(run_id=run_id)
    assert len(records) == 1
    assert records[0].company == "Epic Systems"
    assert records[0].revenue_usd_millions == 4000.0
    assert records[0].gross_margin_pct == 72.0
