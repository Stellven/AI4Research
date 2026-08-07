import { SpreadsheetFile, Workbook } from '@oai/artifact-tool';
const wb = Workbook.create();
const sh = wb.worksheets.add('Report');
sh.getRange('A1:A3').values = [['Same'], ['Same'], ['Same']];
sh.getRange('A1:A3').merge();
const out = await SpreadsheetFile.exportXlsx(wb);
// Disabled: the original wrote to a specific developer's absolute path and had
// no assertions, so it was an ad-hoc artifact probe rather than a valid test.
await out.save('/disabled/nonportable/test_merge.xlsx');
