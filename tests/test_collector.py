from datetime import UTC, datetime

from assistant.collector import collect
from assistant.models import Interest, Item, Settings, SourceSpec
from assistant.sources import REGISTRY


class _FakeSource:
    def fetch(self, spec: SourceSpec, limit: int) -> list[Item]:
        return [
            Item(title="없음", url="https://x/0"),
            Item(title="옛날", url="https://x/1", published=datetime(2026, 1, 1, tzinfo=UTC)),
            Item(title="최신", url="https://x/2", published=datetime(2026, 10, 1, tzinfo=UTC)),
        ]


class _BrokenSource:
    def fetch(self, spec: SourceSpec, limit: int) -> list[Item]:
        raise RuntimeError("boom")


def test_collect_sorts_newest_first_and_undated_last(monkeypatch) -> None:
    monkeypatch.setitem(REGISTRY, "fake", _FakeSource)
    settings = Settings(
        interests=(Interest(name="T", sources=(SourceSpec(type="fake", url="x"),)),)
    )
    digests = collect(settings)
    assert [i.title for i in digests[0].items] == ["최신", "옛날", "없음"]


def test_collect_continues_when_a_source_fails(monkeypatch) -> None:
    monkeypatch.setitem(REGISTRY, "fake", _FakeSource)
    monkeypatch.setitem(REGISTRY, "broken", _BrokenSource)
    settings = Settings(
        interests=(
            Interest(
                name="T",
                sources=(SourceSpec(type="broken", url="x"), SourceSpec(type="fake", url="y")),
            ),
        )
    )
    digests = collect(settings)
    assert len(digests[0].items) == 3
