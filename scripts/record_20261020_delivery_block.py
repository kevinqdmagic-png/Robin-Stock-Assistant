#!/usr/bin/env python3
"""Append the observed Railway build outage; do not rewrite finished analysis."""
from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SHA = '2fdcd081781a0df535fffd1ea177430a4e81813a'
OLD = '6d1c4fd870cff30c8694c79a9a88d146313f941e'
SOURCE = 'https://status.railway.com/incident/JUA1PC5H'


def main():
    runs_path = ROOT / 'backend/data/task_runs.json'
    runs = json.loads(runs_path.read_text())
    now = datetime.now(timezone.utc)
    utc, cn = now.isoformat(timespec='seconds'), now.astimezone(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
    appended = []
    for task in ('volume_price', 'low_position', 'dragon_tiger', 'combined_pair', 'limitup_single'):
        run = ('limitup-single-20261021-scheduled-v2' if task == 'limitup_single'
               else task.replace('_', '-') + '-20261020-scheduled-close-v1')
        original = next(r for r in runs['items'] if r['run_id'] == run and r['status'] == 'completed')
        event_id = run + '-delivery-blocked-railway-build-pause'
        if any(r['id'] == event_id for r in runs['items']):
            continue
        runs['items'].append({
            'id': event_id, 'run_id': run, 'task_id': task, 'date': original['date'], 'trigger': 'scheduled',
            'started_at': original['started_at'], 'recorded_at': utc, 'completed_at': utc, 'status': 'blocked',
            'summary': '完整分析与原样本已归档，164项测试、research及容器核验通过；Railway全平台暂停新构建，准确SHA发布未创建新部署，APP尚未同步。',
            'report_ids': original['report_ids'], 'recommendation_ids': original.get('recommendation_ids', []),
            'analysis_completed': True, 'delivery_status': 'blocked_transient_platform_build_outage',
            'requested_commit': SHA, 'configured_source_commit_readback': SHA, 'observed_production_commit': OLD,
            'deployment_id': None, 'tool_error': 'Deploys have been paused temporarily',
            'sources': [SOURCE, 'docs/research/combined-pair-20261020-delivery-blocked.json']})
        appended.append(event_id)
    if not appended:
        print('Same delivery outage already recorded; no duplicate.'); return
    audit = {
        'recorded_at': utc, 'time_cn': cn, 'market_date': '2026-10-20', 'planned_entry_date': '2026-10-21',
        'research_commit': SHA, 'research_workflow_run': 39469718401, 'research_job': 'success',
        'local_unit_tests': {'passed': 164, 'failed': 0}, 'container_check': 'success',
        'production_check': 'in_progress_waiting_for_new_release', 'delivery_status': 'blocked',
        'tool_error': 'Deploys have been paused temporarily', 'tool_error_code': 'INVALID_ARGUMENT',
        'source_pin_readback': SHA, 'deployment_id_returned': None,
        'latest_successful_deployment': '928d0dd9-8fa3-4c75-8f71-9839d5f57388',
        'observed_production_sha': OLD, 'production_health_time_cn': '2026-10-21T01:53:30+08:00',
        'missing_live_report_ids': ['volume-price-20261020-close-v1', 'low-position-20261020-close-v1',
                                    'dragon-tiger-20261020-close-v1', 'combined-pair-20261020-close-v1',
                                    'limitup-single-20261021-review-v2'],
        'official_incident': SOURCE, 'official_latest_update_utc': '2026-10-20T17:18:00+00:00',
        'incident_scope': 'all workspaces: new builds paused; running services not affected',
        'no_retry_or_bypass': True, 'existing_staged_source_changes_not_accepted': True,
        'transient_failure_does_not_change_task_schedule_or_enabled_state': True,
        'analysis_and_original_conditions_unchanged': True, 'receipt_ids': appended}
    runs_path.write_text(json.dumps(runs, ensure_ascii=False, indent=2) + '\n')
    target = ROOT / 'docs/research/combined-pair-20261020-delivery-blocked.json'
    target.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
