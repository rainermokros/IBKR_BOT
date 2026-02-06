"""
Tests for data quality monitoring system.
"""

import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from src.v6.data.quality_monitor import (
    DataQualityMonitor,
    DataQualityReport,
    QualityIssue,
    Severity,

)


class TestQualityIssue:
    """Test QualityIssue data model."""

    def test_create_issue(self):
        """Test creating a quality issue."""
        issue = QualityIssue(
            category="completeness",
            severity=Severity.ERROR,
            description="Test issue",
            table="test_table",
            affected_rows=10,
        )

        assert issue.category == "completeness"
        assert issue.severity == Severity.ERROR
        assert issue.description == "Test issue"
        assert issue.affected_rows == 10

    def test_issue_to_dict(self):
        """Test converting issue to dictionary."""
        issue = QualityIssue(
            category="accuracy",
            severity=Severity.WARNING,
            description="Test warning",
            table="test_table",
        )

        issue_dict = issue.to_dict()

        assert issue_dict["category"] == "accuracy"
        assert issue_dict["severity"] == "WARNING"
        assert issue_dict["description"] == "Test warning"
        assert "timestamp" in issue_dict


class TestDataQualityReport:
    """Test DataQualityReport functionality."""

    def test_create_report(self):
        """Test creating a quality report."""
        report = DataQualityReport()

        assert report.overall_score == 100.0
        assert len(report.issues) == 0
        assert not report.has_critical_issues()
        assert not report.has_errors()

    def test_add_info_issue(self):
        """Test adding INFO issue doesn't affect score."""
        report = DataQualityReport()

        issue = QualityIssue(
            category="completeness",
            severity=Severity.INFO,
            description="Info message",
            table="test",
        )
        report.add_issue(issue)

        assert report.overall_score == 100.0
        assert len(report.issues) == 1

    def test_add_warning_issue(self):
        """Test adding WARNING issue reduces score."""
        report = DataQualityReport()

        issue = QualityIssue(
            category="completeness",
            severity=Severity.WARNING,
            description="Warning message",
            table="test",
        )
        report.add_issue(issue)

        assert report.overall_score == 99.0
        assert len(report.issues) == 1

    def test_add_error_issue(self):
        """Test adding ERROR issue reduces score."""
        report = DataQualityReport()

        issue = QualityIssue(
            category="accuracy",
            severity=Severity.ERROR,
            description="Error message",
            table="test",
        )
        report.add_issue(issue)

        assert report.overall_score == 95.0
        assert report.has_errors()

    def test_add_critical_issue(self):
        """Test adding CRITICAL issue reduces score significantly."""
        report = DataQualityReport()

        issue = QualityIssue(
            category="timeliness",
            severity=Severity.CRITICAL,
            description="Critical message",
            table="test",
        )
        report.add_issue(issue)

        assert report.overall_score == 80.0
        assert report.has_critical_issues()
        assert report.has_errors()

    def test_score_clamping(self):
        """Test score is clamped between 0 and 100."""
        report = DataQualityReport()

        # Add many critical issues
        for _ in range(10):
            issue = QualityIssue(
                category="test",
                severity=Severity.CRITICAL,
                description="Critical",
                table="test",
            )
            report.add_issue(issue)

        # Score should not go below 0
        assert report.overall_score == 0.0

    def test_get_issues_by_severity(self):
        """Test filtering issues by severity."""
        report = DataQualityReport()

        # Add issues of different severities
        for severity in [Severity.INFO, Severity.WARNING, Severity.ERROR, Severity.CRITICAL]:
            issue = QualityIssue(
                category="test",
                severity=severity,
                description=f"{severity.value} issue",
                table="test",
            )
            report.add_issue(issue)

        critical_issues = report.get_issues_by_severity(Severity.CRITICAL)
        assert len(critical_issues) == 1
        assert critical_issues[0].severity == Severity.CRITICAL

        warning_issues = report.get_issues_by_severity(Severity.WARNING)
        assert len(warning_issues) == 1

    def test_summary(self):
        """Test report summary."""
        report = DataQualityReport()

        # Add some issues
        for _ in range(2):
            report.add_issue(
                QualityIssue(
                    category="test",
                    severity=Severity.CRITICAL,
                    description="Critical",
                    table="test",
                )
            )

        for _ in range(3):
            report.add_issue(
                QualityIssue(
                    category="test",
                    severity=Severity.ERROR,
                    description="Error",
                    table="test",
                )
            )

        for _ in range(4):
            report.add_issue(
                QualityIssue(
                    category="test",
                    severity=Severity.WARNING,
                    description="Warning",
                    table="test",
                )
            )

        summary = report.summary()
        assert "41.0/100" in summary  # 100 - 20*2 - 5*3 - 1*4 = 41
        assert "Critical: 2" in summary
        assert "Errors: 3" in summary
        assert "Warnings: 4" in summary


class TestDataQualityMonitor:
    """Test DataQualityMonitor functionality."""

    def test_init_default_data_dir(self):
        """Test initializing monitor with default data directory."""
        monitor = DataQualityMonitor()

        assert monitor.data_dir is not None
        assert monitor.data_dir.name == "lake"

    def test_init_custom_data_dir(self):
        """Test initializing monitor with custom data directory."""
        custom_dir = Path("/tmp/test_data")
        monitor = DataQualityMonitor(data_dir=custom_dir)

        assert monitor.data_dir == custom_dir

    @pytest.mark.asyncio
    async def test_check_option_snapshots_completeness_no_table(self):
        """Test completeness check when table doesn't exist."""
        monitor = DataQualityMonitor(data_dir=Path("/nonexistent"))

        issues = await monitor.check_option_snapshots_completeness()

        assert len(issues) == 1
        assert issues[0].severity == Severity.CRITICAL
        assert "does not exist" in issues[0].description

    @pytest.mark.asyncio
    async def test_check_data_freshness_no_table(self):
        """Test freshness check when table doesn't exist."""
        monitor = DataQualityMonitor(data_dir=Path("/nonexistent"))

        issues = await monitor.check_data_freshness()

        # Should return empty list (graceful handling)
        assert len(issues) == 0


class TestIntegration:
    """Integration tests for data quality monitoring."""

    @pytest.mark.asyncio
    async def test_generate_report_with_no_data(self):
        """Test generating report with no data directory."""
        monitor = DataQualityMonitor(data_dir=Path("/nonexistent"))

        report = await monitor.generate_report()

        # Should handle gracefully and return a report
        assert isinstance(report, DataQualityReport)
        assert isinstance(report.overall_score, float)

    @pytest.mark.asyncio
    async def test_report_to_dict(self):
        """Test converting report to dictionary."""
        report = DataQualityReport()

        issue = QualityIssue(
            category="test",
            severity=Severity.WARNING,
            description="Test",
            table="test_table",
        )
        report.add_issue(issue)

        report_dict = report.to_dict()

        assert report_dict["overall_score"] == 99.0
        assert report_dict["total_issues"] == 1
        assert report_dict["warning_issues"] == 1
        assert len(report_dict["issues"]) == 1
