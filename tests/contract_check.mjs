#!/usr/bin/env node
/** Validate live API responses against the authoritative OpenAPI schemas.
 * Uses the frontend's already-installed YAML and AJV dependencies so QA does not
 * depend on a separate Python package installation.
 */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'frontend/package.json'));
const yaml = require('js-yaml');
const Ajv2020 = require('@redocly/ajv/dist/2020').default;

function normalize(schema) {
  if (Array.isArray(schema)) return schema.map(normalize);
  if (!schema || typeof schema !== 'object') return schema;
  const value = Object.fromEntries(Object.entries(schema)
    .filter(([key]) => key !== 'nullable')
    .map(([key, item]) => [key, normalize(item)]));
  if (schema.nullable) {
    if (typeof value.type === 'string') value.type = [value.type, 'null'];
    else if (Array.isArray(value.type) && !value.type.includes('null')) value.type.push('null');
    else if (!value.type) return { anyOf: [value, { type: 'null' }] };
  }
  return value;
}

function validate(document, name, payload) {
  const schema = { ...document, $schema: 'https://json-schema.org/draft/2020-12/schema', $ref: `#/components/schemas/${name}` };
  const ajv = new Ajv2020({ allErrors: true, strict: false, validateFormats: false });
  const check = ajv.compile(normalize(schema));
  if (!check(payload)) {
    const details = check.errors.slice(0, 10).map(error => `${error.instancePath || '/'} ${error.message}`).join('\n');
    throw new Error(`${name} does not match the contract:\n${details}`);
  }
  console.log(`${name}: valid`);
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url} returned HTTP ${response.status}`);
  return response.json();
}

async function main() {
  const args = process.argv.slice(2);
  const value = (name, fallback) => {
    const index = args.indexOf(name);
    return index >= 0 ? args[index + 1] : fallback;
  };
  const contractPath = path.resolve(value('--contract', path.join(root, 'shared/openapi.yaml')));
  const caseId = value('--case-id', null);
  const baseUrl = value('--base-url', 'http://127.0.0.1:8000/api/v1').replace(/\/$/, '');
  const payloadPath = value('--payload-file', null);
  const policyPath = value('--policy-file', null);
  const document = yaml.load(fs.readFileSync(contractPath, 'utf8'));
  const ajv = new Ajv2020({ allErrors: true, strict: false, validateFormats: false });
  const normalized = normalize({ ...document, $schema: 'https://json-schema.org/draft/2020-12/schema' });
  ajv.addSchema(normalized);

  let result;
  let trace;
  if (payloadPath) {
    result = JSON.parse(fs.readFileSync(path.resolve(payloadPath), 'utf8'));
    trace = { case_id: result.case_id, events: result.trace || [] };
  } else {
    if (!caseId) throw new Error('Pass --case-id for a live API check, or --payload-file for a saved synthetic response.');
    result = await fetchJson(`${baseUrl}/disputes/${encodeURIComponent(caseId)}`);
    trace = await fetchJson(`${baseUrl}/disputes/${encodeURIComponent(caseId)}/trace`);
  }
  validate(document, 'CaseResult', result);
  validate(document, 'AdjudicationTrace', trace);

  const policy = policyPath
    ? JSON.parse(fs.readFileSync(path.resolve(policyPath), 'utf8'))
    : await fetchJson(`${baseUrl}/policy/${encodeURIComponent(result.policy_version)}`);
  validate(document, 'PolicyDocument', policy);
}

main().catch(error => {
  console.error(error.message);
  process.exitCode = 1;
});
