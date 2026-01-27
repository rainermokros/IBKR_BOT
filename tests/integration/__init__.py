"""Integration tests for v6 trading system.

This package contains end-to-end integration tests that validate
complete trading workflows with mock IB connections.

Test categories:
- Entry to monitoring: Entry workflow → position sync → monitoring
- Monitoring to exit: Decisions → exit workflow → position close
- Full lifecycle: Complete trade from signal to exit
- Component integration: Decision engine + execution, risk + workflows
- Alerts integration: Decision rules → alerts → dashboard
"""
