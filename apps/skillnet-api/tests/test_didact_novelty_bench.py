from scripts import didact_novelty_bench as bench


def test_bench_compares_complete_catalog_without_runtime_activation() -> None:
    report = bench.run(scenarios=24)

    assert report["catalog_count"] == 34
    assert report["runtime_connected"] is False
    assert report["rows"]
    assert all(row["eligibility_preserved"] for row in report["rows"])
    assert report["bounded_novelty"]["unique_top_components"] >= report["current"][
        "unique_top_components"
    ]
