import fs from 'node:fs/promises';
import path from 'node:path';
import { SpreadsheetFile, Workbook } from '@oai/artifact-tool';

const args = process.argv.slice(2);
const arg = (name) => {
  const index = args.indexOf(name);
  if (index < 0 || !args[index + 1]) throw new Error(`Missing ${name}`);
  return args[index + 1];
};
const queuePath = path.resolve(arg('--queue'));
const auditPath = path.resolve(arg('--audit'));
const calibrationPath = path.resolve(arg('--calibration'));
const outputPath = path.resolve(arg('--output'));
const outputDir = path.dirname(outputPath);
const queue = (await fs.readFile(queuePath, 'utf8')).split(/\r?\n/).filter(Boolean).map(JSON.parse);
const audits = (await fs.readFile(auditPath, 'utf8')).split(/\r?\n/).filter(Boolean).map(JSON.parse);
const calibration = JSON.parse(await fs.readFile(calibrationPath, 'utf8'));
if (queue.length !== 60 || audits.length !== 90) throw new Error('Expected 60 training cases and 90 agent audit rows');

const compact = (value) => JSON.stringify(value ?? {}, null, 2);
const jsonFromTarget = (target) => {
  const content = target?.messages?.at(-1)?.content;
  if (!content) return '{}';
  try { return JSON.stringify(JSON.parse(content), null, 2); } catch { return content; }
};
function context(sample) {
  const { filing, records } = sample;
  const ride = records.ride || {};
  const route = records.route || {};
  const fare = records.fare || {};
  const money = (cents) => cents == null ? 'not recorded' : `S$${(cents / 100).toFixed(2)}`;
  return [
    `${filing.category.replaceAll('_', ' ')} · filed by ${filing.filed_by}`,
    filing.description,
    `Trip: ${ride.status || 'unknown'}; service ${ride.service_tier || 'unknown'}; quoted ${money(ride.quoted_fare_cents)}; charged ${money(ride.charged_fare_cents)}.`,
    `Route: ${route.planned_distance_km ?? 'unknown'} km planned / ${route.actual_distance_km ?? 'unknown'} km recorded.`,
    `Cancellation: ${ride.cancellation_actor || 'not recorded'} at ${ride.cancellation_timestamp || 'not recorded'}; wait ${ride.driver_waited_seconds ?? 'not recorded'} seconds.`,
    `Filed ${filing.filed_at}. Scenario tags: ${(sample.tags || []).join(', ') || 'none'}.`,
  ].filter(Boolean).join('\n');
}
function sourceSummary(prompt) {
  const evidence = (prompt.evidence_records || []).map((item) => {
    const payload = item.payload || {};
    const verification = payload.verification_status || (payload.synthetic ? 'synthetic system record' : 'not specified');
    const money = (cents) => cents == null ? 'not recorded' : `S$${(cents / 100).toFixed(2)}`;
    let summary;
    switch (item.record_type) {
      case 'ride':
        summary = [`Status: ${payload.status || 'unknown'}; service: ${payload.service_tier || 'unknown'}.`,
          `Fare quoted: ${money(payload.quoted_fare_cents)}; charged: ${money(payload.charged_fare_cents)}.`,
          `Cancellation: ${payload.cancellation_actor || 'not recorded'} · ${payload.cancellation_timestamp || 'not recorded'}.`,
          `Scheduled: ${payload.scheduled_at || 'not recorded'}; matched: ${payload.accepted_at || 'not recorded'}.`].join('\n');
        break;
      case 'route':
        summary = [`${payload.pickup_label || 'Pickup not recorded'} → ${payload.dropoff_label || 'drop-off not recorded'}.`,
          `Distance: ${payload.planned_distance_km ?? 'unknown'} km planned / ${payload.actual_distance_km ?? 'unknown'} km recorded.`,
          `Driver arrival: ${payload.driver_arrival_at || 'not recorded'}; wait: ${payload.driver_wait_seconds ?? 'unknown'} seconds.`].join('\n');
        break;
      case 'gps':
        summary = [`${(payload.samples || []).length} GPS samples recorded; nearest recorded distance to pickup: ${payload.min_distance_to_pickup_m ?? 'unknown'} m.`,
          ...(payload.samples || []).map((sample) => `${sample.at || 'time unknown'} · ${sample.status || 'status unknown'} · ${sample.lat ?? 'lat unknown'}, ${sample.lon ?? 'lon unknown'} · accuracy ${sample.accuracy_m ?? 'unknown'} m`) ].join('\n');
        break;
      case 'chat':
        summary = (payload.messages || []).map((message) => `${message.role || 'Unknown sender'} · ${message.at || 'time unknown'}: ${message.text || ''}`).join('\n') || 'No messages recorded.';
        break;
      case 'fare':
        summary = [`Total recorded: ${money(payload.total_fare_cents)}; cancellation fee: ${money(payload.cancellation_fee_cents)}; waiting fee: ${money(payload.waiting_fare_cents)}.`,
          `Components: ${(payload.components || []).map((part) => `${part.name}: ${money(part.amount_cents)}`).join('; ') || 'none recorded'}.`].join('\n');
        break;
      case 'events':
        summary = (payload || []).map((event) => `${event.event_at || 'time unknown'} · ${(event.event_type || 'event').replaceAll('_', ' ')} · ${event.details || ''}`).join('\n') || 'No app events recorded.';
        break;
      default:
        summary = compact(payload);
    }
    return `${item.evidence_id} · ${item.record_type} · ${verification}\n${summary}`;
  }).join('\n\n');
  const policies = (prompt.policy_rules || []).map((rule) => {
    const source = rule.source || {};
    return `${rule.id} · ${rule.section}: ${rule.text}${source.title ? `\n${source.title} — ${source.url}` : ''}`;
  }).join('\n\n');
  return { evidence, policies };
}
function caseRow(row) {
  const sample = row.sample;
  const prompt = JSON.parse(row.role_targets.judge.messages[0].content);
  const refs = (prompt.policy_rules || []).map((rule) => `${rule.id}: ${rule.text}`).join('\n');
  const ev = sourceSummary(prompt).evidence;
  return [sample.sample_id, row.split, sample.scenario_family, sample.filing.category,
    sample.filing.filed_by, context(sample), ev, refs,
    compact(row.ruling_target || JSON.parse(row.role_targets.judge.messages.at(-1).content)),
    'Pending', '', '', '', sample.policy_version, ''];
}
function agentRow(row, role) {
  const sample = row.sample;
  const target = row.role_targets[role];
  const prompt = JSON.parse(target.messages[0].content);
  const source = sourceSummary(prompt);
  return [sample.sample_id, row.split, sample.scenario_family, sample.filing.category,
    role, context(sample), `${source.evidence}\n\nPOLICY\n${source.policies}`,
    jsonFromTarget(target), 'Pending', '', '', '', sample.policy_version, ''];
}
const providerLabel = (output, role) => {
  if (role === 'judge') return output?.judge?.provider?.model || output?.model_proposed_ruling?.provider?.model || 'not recorded';
  return output?.provider?.model || output?.provider?.kind || 'not recorded';
};
const auditRows = audits.map((row) => [
  row.sample_key, row.scenario_group, row.scenario_family, row.category, row.role,
  providerLabel(row.agent_output, row.role), row.source_policy_version,
  row.role === 'judge' ? row.confidence : '', compact(row.agent_output),
  '', '', '', '', '', '', '', '',
]);

const workbook = Workbook.create();
const overview = workbook.worksheets.add('Overview');
const rulings = workbook.worksheets.add('Rulings');
const agents = workbook.worksheets.add('Agent Targets');
const liveAudit = workbook.worksheets.add('Live Output Audit');
for (const sheet of [overview, rulings, agents, liveAudit]) sheet.showGridLines = false;

overview.getRange('A2:F2').merge();
overview.getRange('A2').values = [['Ryde Tribunal · Human Review']];
overview.getRange('A2:F2').format = { font: { name: 'Arial', size: 16, bold: true, color: '#153B3A' } };
overview.getRange('A4:C13').values = [
  ['Review package', '', 'Policy 1.1.0 · synthetic cases only'],
  ['Training queue', '', '60 cases · 40 train / 10 validation / 10 test'],
  ['Separate decisions', '', '60 rulings and 180 core-agent targets'],
  ['Core agents', '', 'Rider Advocate · Driver Advocate · Judge'],
  ['Live output audit', '', '30 cases · 90 agent rows · saved outputs only'],
  ['Provider calls', '', 'None for this package'],
  ['Historical output policy', '', calibration.source_policy_version],
  ['Current escalation threshold', '', calibration.current_escalation_threshold],
  ['Saved benchmark accuracy', '', calibration.exact_outcome_accuracy],
  ['Confidence Brier score', '', calibration.all_case_confidence.brier_score],
];
overview.getRange('A4:A13').format.font = { name: 'Arial', size: 10, bold: true, color: '#233B3A' };
overview.getRange('A4:C13').format.wrapText = true;
overview.getRange('A4:A13').format.columnWidth = 29;
overview.getRange('B4:B13').format.columnWidth = 5;
overview.getRange('C4:C13').format.columnWidth = 84;
overview.getRange('C12:C13').format.numberFormat = '0.0000';
overview.getRange('A14:C14').values = [['Expected calibration error', '', calibration.all_case_confidence.expected_calibration_error]];
overview.getRange('A14').format.font = { name: 'Arial', size: 10, bold: true, color: '#233B3A' };
overview.getRange('C14').format.numberFormat = '0.0000';
overview.getRange('A15:F15').merge();
overview.getRange('A15').values = [['How to complete the review']];
overview.getRange('A15:F15').format = { fill: '#DDEFEA', font: { name: 'Arial', size: 11, bold: true, color: '#153B3A' } };
overview.getRange('B16:C22').values = [
  ['1', 'Review each ruling separately from all agent targets. A ruling approval does not approve the Judge transcript.'],
  ['2', 'Choose Pending, Approve, Correct, or Reject in the Decision column. For Correct, provide valid JSON in the correction column.'],
  ['3', 'For every approval or correction, fill Reviewer, Reviewed at (ISO 8601 with timezone), Policy version, and Rationale.'],
  ['4', 'Check claims against the supplied evidence records and policy text. Do not treat party statements as verified facts.'],
  ['5', 'On Live Output Audit, score evidence use, citation accuracy, policy use, and fairness from 1 (poor) to 5 (strong). Record unsupported claims and rationale.'],
  ['6', 'The saved benchmark outputs use policy 1.0.0. Their calibration is diagnostic only; do not use these cases or labels as training data.'],
  ['7', 'Keep unresolved or rejected rulings out of training. The current confidence threshold stays at 0.70.'],
];
overview.getRange('B16:B22').format.font = { name: 'Arial', size: 10, bold: true, color: '#0F766E' };
overview.getRange('C16:C22').format = { font: { name: 'Arial', size: 10, color: '#243B3A' }, wrapText: true, verticalAlignment: 'center' };
overview.getRange('B16:B22').format.columnWidth = 5;
overview.getRange('C16:C22').format.columnWidth = 110;
overview.getRange('B16:C22').format.rowHeight = 37;
overview.getRange('A24').values = [['Calibration metric']];
overview.getRange('C24:D24').merge();
overview.getRange('C24').values = [['Saved live responses · full 120-case set']];
overview.getRange('A24:D24').format = { fill: '#153B3A', font: { name: 'Arial', size: 10, bold: true, color: '#FFFFFF' } };
const bands = calibration.all_case_confidence.bands.map((band) => [band.range, band.count, band.mean_confidence, band.accuracy]);
overview.getRange(`A25:D${25 + bands.length}`).values = [['Confidence range', 'Cases', 'Mean confidence', 'Outcome accuracy'], ...bands];
overview.getRange(`A25:D${25 + bands.length}`).format = { font: { name: 'Arial', size: 10, color: '#243B3A' } };
overview.getRange(`A25:D25`).format = { fill: '#E9F3F1', font: { name: 'Arial', size: 10, bold: true, color: '#153B3A' } };
overview.getRange(`C26:D${25 + bands.length}`).format.numberFormat = '0.0%';
overview.freezePanes.freezeRows(2);

const rulingHeaders = ['Sample ID', 'Split', 'Scenario family', 'Category', 'Filed by', 'Case summary',
  'Evidence records', 'Policy rules supplied', 'Draft ruling JSON', 'Decision', 'Corrected ruling JSON',
  'Reviewer', 'Reviewed at (ISO 8601)', 'Policy version', 'Rationale'];
rulings.getRangeByIndexes(0, 0, 1, rulingHeaders.length).values = [rulingHeaders];
rulings.getRangeByIndexes(1, 0, queue.length, rulingHeaders.length).values = queue.map(caseRow);
const agentHeaders = ['Sample ID', 'Split', 'Scenario family', 'Category', 'Agent role', 'Case summary',
  'Evidence and policy prompt context', 'Proposed target JSON', 'Decision', 'Corrected target JSON',
  'Reviewer', 'Reviewed at (ISO 8601)', 'Policy version', 'Rationale'];
agents.getRangeByIndexes(0, 0, 1, agentHeaders.length).values = [agentHeaders];
const agentData = queue.flatMap((row) => ['rider_advocate', 'driver_advocate', 'judge'].map((role) => agentRow(row, role)));
agents.getRangeByIndexes(1, 0, agentData.length, agentHeaders.length).values = agentData;
const auditHeaders = ['Sample key', 'Scenario group', 'Scenario family', 'Category', 'Agent role', 'Provider/model',
  'Output policy', 'Judge confidence', 'Saved agent output JSON', 'Evidence use (1–5)',
  'Citation accuracy (1–5)', 'Policy use (1–5)', 'Fairness (1–5)', 'Unsupported claims handling (1–5)',
  'Issue notes', 'Reviewer', 'Rationale'];
liveAudit.getRangeByIndexes(0, 0, 1, auditHeaders.length).values = [auditHeaders];
liveAudit.getRangeByIndexes(1, 0, auditRows.length, auditHeaders.length).values = auditRows;

function styleTable(sheet, lastColumn, lastRow, widths, freezeColumns = 1) {
  const columnLabel = (number) => {
    let label = '';
    while (number > 0) { const rem = (number - 1) % 26; label = String.fromCharCode(65 + rem) + label; number = Math.floor((number - 1) / 26); }
    return label;
  };
  const end = columnLabel(lastColumn);
  sheet.getRange(`A1:${end}1`).format = {
    fill: '#153B3A', font: { name: 'Arial', size: 10, bold: true, color: '#FFFFFF' },
    wrapText: true, verticalAlignment: 'center',
  };
  sheet.getRange(`A1:${end}${lastRow}`).format.font = { name: 'Arial', size: 9, color: '#263C3A' };
  sheet.getRange(`A1:${end}${lastRow}`).format.verticalAlignment = 'center';
  sheet.getRange(`A2:${end}${lastRow}`).format.wrapText = true;
  Object.entries(widths).forEach(([column, width]) => {
    sheet.getRange(`${column}1:${column}${lastRow}`).format.columnWidth = width;
  });
  sheet.getRange(`A2:${end}${lastRow}`).format.rowHeight = 80;
  sheet.getRange(`A1:${end}1`).format.rowHeight = 34;
  sheet.freezePanes.freezeRows(1);
  if (freezeColumns > 1) sheet.freezePanes.freezeColumns(freezeColumns);
  sheet.tables.add(`A1:${end}${lastRow}`, true, `${sheet.name.replaceAll(' ', '')}Table`);
}
styleTable(rulings, rulingHeaders.length, queue.length + 1,
  { A: 15, B: 13, C: 24, D: 22, E: 13, F: 52, G: 60, H: 58, I: 56, J: 15, K: 56, L: 22, M: 27, N: 22, O: 42 }, 2);
styleTable(agents, agentHeaders.length, agentData.length + 1,
  { A: 15, B: 13, C: 24, D: 22, E: 21, F: 52, G: 62, H: 56, I: 15, J: 56, K: 22, L: 27, M: 22, N: 42 }, 2);
styleTable(liveAudit, auditHeaders.length, auditRows.length + 1,
  { A: 16, B: 26, C: 28, D: 22, E: 20, F: 28, G: 21, H: 17, I: 58, J: 18, K: 22, L: 17, M: 17, N: 22, O: 46, P: 22, Q: 42 }, 2);

for (const [sheet, range] of [[rulings, `J2:J${queue.length + 1}`],
  [agents, `I2:I${agentData.length + 1}`]]) {
  sheet.getRange(range).dataValidation = { rule: { type: 'list', values: ['Pending', 'Approve', 'Correct', 'Reject'] } };
  sheet.getRange(range).format.fill = '#FFF2CC';
}
liveAudit.getRange(`J2:N${auditRows.length + 1}`).dataValidation = {
  rule: { type: 'whole', operator: 'between', formula1: 1, formula2: 5 },
};
liveAudit.getRange(`J2:N${auditRows.length + 1}`).format.fill = '#FFF2CC';
for (const [sheet, range] of [[rulings, `K2:O${queue.length + 1}`], [agents, `J2:N${agentData.length + 1}`],
  [liveAudit, `O2:Q${auditRows.length + 1}`]]) sheet.getRange(range).format.fill = '#FFF9E8';

workbook.recalculate();
const inspect = await workbook.inspect({ kind: 'sheet', include: 'id,name', maxChars: 2500 });
console.log(inspect.ndjson);
await fs.mkdir(outputDir, { recursive: true });
for (const [sheetName, range] of [['Overview', 'A1:F27'], ['Rulings', 'A1:O5'],
  ['Agent Targets', 'A1:N5'], ['Live Output Audit', 'A1:Q5']]) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: 'png' });
  const safeName = sheetName.toLowerCase().replaceAll(' ', '-');
  await fs.writeFile(path.join(outputDir, `${safeName}-preview.png`), new Uint8Array(await preview.arrayBuffer()));
}
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(`Saved ${outputPath}`);
