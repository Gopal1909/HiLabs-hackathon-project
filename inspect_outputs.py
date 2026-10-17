"""Quick inspection of C1 outputs."""
import pandas as pd
import json

# Load summary
with open('outputs/index_parsing_summary.json') as f:
    s = json.load(f)

print('=== SUMMARY JSON ===')
print('run_timestamp:', s['run_timestamp'])
print('index_files_attempted:', s['index_files_attempted'])
print('index_files_ok:', s['index_files_ok'])
print('index_files_failed:', s['index_files_failed'])
print('total_plan_file_rows:', s['total_plan_file_rows'])
print('unique_rate_file_urls:', s['unique_rate_file_urls'])
print('plan_rows_with_ppo:', s['plan_rows_with_ppo'])
print('rows_skipped:', s['rows_skipped'])
print()
print('Brand row counts:')
for k, v in sorted(s['brand_row_counts'].items()):
    print('  %s: %d' % (k, v))
print('Market type counts:')
for k, v in sorted(s['market_type_counts'].items()):
    print('  %s: %d' % (k, v))
print('Network type counts:')
for k, v in sorted(s['network_type_counts'].items()):
    print('  %s: %d' % (k, v))
print()
print('=== INDEX FILE RESULTS ===')
for r in s['index_file_results']:
    print('  %-30s status=%-12s rows=%5d  skipped=%d' % (
        r['brand'], r['fetch_status'], r['rows_parsed'], r['rows_skipped']))

pi = pd.read_csv('outputs/plan_index.csv')
uf = pd.read_csv('outputs/unique_rate_files.csv')

print()
print('=== UNIQUE RATE FILES (%d total) ===' % len(uf))
cols = ['rate_file_fingerprint', 'rate_file_url', 'file_type', 'plan_count', 'brand_list', 'market_types', 'network_types']
print(uf[cols].to_string())

print()
hn = pi[pi['brand'] == 'Health Net']
print('=== Health Net file descriptions (unique) ===')
print(hn[['file_description', 'file_type', 'rate_file_url', 'network_type']].drop_duplicates(['file_description', 'rate_file_url']).to_string())

print()
hn_ppo = pi[(pi['brand'] == 'Health Net') & (pi['network_type'] == 'PPO') & (pi['plan_market_type'] == 'group')]
print('Health Net PPO group plans (unique plan_id):', hn_ppo['plan_id'].nunique())
print('Health Net PPO group rows total:', len(hn_ppo))

# Sample plan names
print('\nSample Health Net PPO group plan names:')
for name in hn_ppo['plan_name'].dropna().unique()[:20]:
    print('  ', name)
