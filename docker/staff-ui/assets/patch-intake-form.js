#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

const ROOT = '/app/.next';

function* walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) yield* walk(full);
    else if (entry.name.endsWith('.js')) yield full;
  }
}

let patchedTitle = 0;
let patchedRequired = 0;

for (const file of walk(ROOT)) {
  let content = fs.readFileSync(file, 'utf8');
  let changed = false;

  // 1. Fix Intake Form Submission Card Title
  if (content.includes('application_reference?.trim()||e.submission_id') || content.includes('application_reference?.trim()||a.submission_id')) {
    const oldClient = 'function G(e){return(0,a.jsx)("span",{className:"font-medium text-[15px]",children:e.application_reference?.trim()||e.submission_id})}function J(e){return e.application_reference??e.submission_id}';
    const newClient = 'function _getCardTitle(e){var fid=(e.record_name&&e.record_name.trim())||e.display_fields?.find(f=>f.field_name==="farmer_id")?.value;var fyd=e.display_fields?.find(f=>f.field_name==="fayda_fan_id"||f.field_name==="fayda_id")?.value;return(fid&&String(fid).trim())||(fyd&&String(fyd).trim())||e.application_reference?.trim()||e.submission_id;}function G(e){return(0,a.jsx)("span",{className:"font-medium text-[15px]",children:_getCardTitle(e)})}function J(e){return _getCardTitle(e)}';

    const oldServer = 'getValue:a=>a.application_reference??a.submission_id,render:a=>(0,d.jsx)("span",{className:"font-medium text-[15px]",children:a.application_reference?.trim()||a.submission_id})}';
    const newServer = 'getValue:a=>{var fid=(a.record_name&&a.record_name.trim())||a.display_fields?.find(f=>f.field_name==="farmer_id")?.value;var fyd=a.display_fields?.find(f=>f.field_name==="fayda_fan_id"||f.field_name==="fayda_id")?.value;return(fid&&String(fid).trim())||(fyd&&String(fyd).trim())||a.application_reference?.trim()||a.submission_id;},render:a=>{var fid=(a.record_name&&a.record_name.trim())||a.display_fields?.find(f=>f.field_name==="farmer_id")?.value;var fyd=a.display_fields?.find(f=>f.field_name==="fayda_fan_id"||f.field_name==="fayda_id")?.value;var title=(fid&&String(fid).trim())||(fyd&&String(fyd).trim())||a.application_reference?.trim()||a.submission_id;return(0,d.jsx)("span",{className:"font-medium text-[15px]",children:title});}}';

    if (content.includes(oldClient)) {
      content = content.replace(oldClient, newClient);
      changed = true;
      patchedTitle++;
    }
    if (content.includes(oldServer)) {
      content = content.replace(oldServer, newServer);
      changed = true;
      patchedTitle++;
    }
  }

  // 2. Fix Section Next Button Required Field Validation
  if (content.includes('skipRequired:!0')) {
    content = content.replaceAll('skipRequired:!0', 'skipRequired:!1');
    changed = true;
    patchedRequired++;
  }

  // 3. Fix Intake Form Cancel Button Navigation Interception
  if (content.includes('r.replace(`${o}?sid=${A}`)') || content.includes('onCancel:()=>r.push(`/intake-form/${b}`)')) {
    if (content.includes('(0,s.useEffect)(()=>{A&&!h&&r.replace(`${o}?sid=${A}`)},[A,h,o,r])')) {
      content = content.replace(
        '(0,s.useEffect)(()=>{A&&!h&&r.replace(`${o}?sid=${A}`)},[A,h,o,r])',
        '(0,s.useEffect)(()=>{if(typeof window!=="undefined"&&window._isCancelingIntakeForm)return;A&&!h&&r.replace(`${o}?sid=${A}`)},[A,h,o,r])'
      );
      changed = true;
    }
    if (content.includes('onCancel:()=>r.push(`/intake-form/${b}`)')) {
      content = content.replace(
        'onCancel:()=>r.push(`/intake-form/${b}`)',
        'onCancel:()=>{if(typeof window!=="undefined"){window._isCancelingIntakeForm=true;window.location.href=`/en/intake-form/${b}`;}else r.push(`/intake-form/${b}`);}'
      );
      changed = true;
    }
  }

  if (changed) {
    fs.writeFileSync(file, content, 'utf8');
    console.log('Patched file:', file);
  }
}

console.log(`Intake Form patch complete. Title patched: ${patchedTitle}, Required validation patched: ${patchedRequired}`);

