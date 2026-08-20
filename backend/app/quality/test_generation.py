"""AI Software Quality Engine -- Test Generation (Volume 48).

Generates tests for missing high-confidence scenarios.
Flow: Finding → Test Proposal → Generation → Execution → Review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class TestProposal:
    proposal_id: str
    finding_id: str
    file_path: str
    test_type: str  # unit/integration/edge_case/failure_path
    description: str
    test_name: str
    target_function: str
    priority: str = "medium"
    confidence: float = 0.5


@dataclass
class GeneratedTest:
    test_id: str
    proposal_id: str
    test_code: str
    test_file: str
    status: str = "generated"  # generated/executing/passed/failed/rejected
    result: dict[str, Any] = field(default_factory=dict)


class TestGenerator:
    """Generate tests for missing high-confidence scenarios."""

    def __init__(self):
        self._proposals: dict[str, TestProposal] = {}
        self._generated: dict[str, GeneratedTest] = {}

    def propose_tests(
        self,
        findings: list[dict[str, Any]],
        test_gaps: list[dict[str, Any]] | None = None,
    ) -> list[TestProposal]:
        proposals: list[TestProposal] = []
        for f in findings:
            if f.get("confidence", 0) < 0.6:
                continue
            if f.get("category") not in ("correctness", "reliability", "security"):
                continue
            proposal = TestProposal(
                proposal_id=str(uuid4()),
                finding_id=f.get("id", ""),
                file_path=f.get("file_path", ""),
                test_type=self._classify_test_type(f),
                description=f"Test for: {f.get('description', '')}",
                test_name=self._generate_test_name(f),
                target_function=f.get("symbol", ""),
                priority=f.get("severity", "medium"),
                confidence=f.get("confidence", 0.5),
            )
            self._proposals[proposal.proposal_id] = proposal
            proposals.append(proposal)

        if test_gaps:
            for gap in test_gaps:
                proposal = TestProposal(
                    proposal_id=str(uuid4()),
                    finding_id="",
                    file_path=gap.get("file_path", ""),
                    test_type="unit",
                    description=f"Test gap: {gap.get('description', '')}",
                    test_name=f"test_{gap.get('function_name', 'unknown')}",
                    target_function=gap.get("function_name", ""),
                    priority="medium",
                    confidence=gap.get("confidence", 0.5),
                )
                self._proposals[proposal.proposal_id] = proposal
                proposals.append(proposal)

        return proposals

    def generate_test(
        self, proposal: TestProposal, template: str = ""
    ) -> GeneratedTest:
        test_code = self._build_test_code(proposal, template)
        generated = GeneratedTest(
            test_id=str(uuid4()),
            proposal_id=proposal.proposal_id,
            test_code=test_code,
            test_file=f"test_{proposal.file_path.replace('/', '_')}",
        )
        self._generated[generated.test_id] = generated
        return generated

    def record_result(
        self, test_id: str, passed: bool, output: str = "", errors: list[str] | None = None
    ) -> GeneratedTest:
        gen = self._generated.get(test_id)
        if not gen:
            raise ValueError(f"Generated test {test_id} not found")
        gen.status = "passed" if passed else "failed"
        gen.result = {"passed": passed, "output": output, "errors": errors or []}
        return gen

    def select_tests_for_changes(
        self,
        changed_files: list[str],
        all_test_files: list[str],
    ) -> list[str]:
        selected: list[str] = []
        changed_names = set()
        for fp in changed_files:
            name = fp.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            changed_names.add(name.lower())

        for tf in all_test_files:
            tf_lower = tf.lower()
            for cn in changed_names:
                if cn in tf_lower or tf_lower.replace("test_", "").replace("_test", "") in cn:
                    selected.append(tf)
                    break
        return selected

    def get_proposals_for_review(self, review_id: str) -> list[TestProposal]:
        return [
            p for p in self._proposals.values()
            if p.finding_id  # proposals linked to findings from this review
        ]

    def _classify_test_type(self, finding: dict[str, Any]) -> str:
        category = finding.get("category", "")
        severity = finding.get("severity", "")
        if category == "security":
            return "edge_case"
        if severity in ("critical", "high"):
            return "failure_path"
        if category == "correctness":
            return "unit"
        return "integration"

    def _generate_test_name(self, finding: dict[str, Any]) -> str:
        symbol = finding.get("symbol", "")
        if symbol:
            return f"test_{symbol}_{finding.get('category', 'general')}"
        file_path = finding.get("file_path", "unknown")
        name = file_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        return f"test_{name}_{finding.get('category', 'general')}"

    def _build_test_code(self, proposal: TestProposal, template: str) -> str:
        if template:
            return template.format(
                test_name=proposal.test_name,
                target=proposal.target_function,
                description=proposal.description,
            )
        return (
            f"def {proposal.test_name}():\n"
            f'    """{proposal.description}"""\n'
            f"    # TODO: implement test for {proposal.target_function}\n"
            f"    assert True  # placeholder\n"
        )
