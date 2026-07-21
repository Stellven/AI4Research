import fs from 'node:fs/promises';
import path from 'node:path';
import { SpreadsheetFile, Workbook } from '@oai/artifact-tool';
const wb = Workbook.create();
const sh = wb.worksheets.add('Report');
sh.getRange('A1:A3').values = [['Same'], ['Same'], ['Same']];
sh.getRange('A1:A3').merge();
const out = await SpreadsheetFile.exportXlsx(wb);
await out.save('/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/outputs/qa_csv_merge/test_merge.xlsx');
