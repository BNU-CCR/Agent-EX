// Run with the bundled artifact-tool runtime; ROOT may be passed as argv[2].
import fs from 'node:fs/promises';
import path from 'node:path';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const root=process.argv[2];if(!root)throw new Error('literature-review root required');
const input=JSON.parse(await fs.readFile(path.join(root,'exports/methods_workbook_input.json'),'utf8'));
const wb=Workbook.create(),summary=wb.worksheets.add('方法研究进度');
const cfg=[['literature_master','文献与方法编码'],['method_venue_map','方法发表地图'],['journal_submission_candidates','双轨投稿'],['method_validation_matrix','验证证据矩阵'],['journals_master','首轮期刊覆盖'],['search_log','检索与核查日志'],['conference_sources','会议来源']];
cfg.push(['venue_coverage_audit','载体覆盖审计']);
const label={record_id:'文献编号',work_id:'研究编号',venue_id:'载体编号',title:'题名或刊名',authors:'作者',language:'语言',venue:'载体',document_type:'文献类型',online_first_date:'首次正式发表',volume_year:'卷期年',date_eligibility:'日期资格',screening_status:'筛选状态',reading_status:'实际阅读',research_object:'研究对象',primary_purpose:'主要用途',method_relevance_tier:'首要方法功能',method_contribution_type:'方法贡献标签',method_maturity:'方法成熟度',disciplinary_home:'实际研究共同体',method_transferability:'方法可迁移性',method_evidence_level:'方法证据等级',method_relevance_rationale:'方法分类理由',method_coding_status:'方法编码证据状态',method_pending_fields:'方法待核字段',method_evidence_location:'方法证据位置',method_last_checked:'方法核查日期',research_question:'研究问题',method_type:'模拟或研究方法',reason:'保留理由',official_url:'官方入口',card_path:'阅读卡'};
const col=n=>{let s='';for(n++;n;n=Math.floor((n-1)/26))s=String.fromCharCode(65+(n-1)%26)+s;return s;};
for(const [key,name]of cfg){
 if(!input[key])continue;const rows=input[key],heads=rows[0],sheet=wb.worksheets.add(name);sheet.showGridLines=false;
 const matrix=rows.map((r,i)=>r.map((v,j)=>{if(!i)return label[v]||v;if(v==='')return null;if(/(?:^|_)date$|^method_last_checked$|^coverage_(?:start|end)$/.test(heads[j])&&/^\d{4}-\d{2}-\d{2}$/.test(v))return new Date(v+'T00:00:00Z');if(/^(?:volume_year|.*_count|confirmed_included|retrieved_count|screened_count)$/.test(heads[j])&&/^\d+$/.test(v))return Number(v);return /^[=+@]/.test(v)?"'"+v:v;}));
 const used=sheet.getRangeByIndexes(0,0,matrix.length,heads.length);used.values=matrix;used.format.font.name='Arial';used.format.font.size=10;used.format.verticalAlignment='top';used.format.columnWidth=24;used.format.rowHeight=46;sheet.freezePanes.freezeRows(1);sheet.freezePanes.freezeColumns(Math.min(3,heads.length));
 const hdr=sheet.getRangeByIndexes(0,0,1,heads.length);hdr.format.fill='#263A5F';hdr.format.font.color='#FFFFFF';hdr.format.font.bold=true;hdr.format.wrapText=true;hdr.format.rowHeight=34;
 for(let j=0;j<heads.length;j++){const k=heads[j],range=sheet.getRangeByIndexes(0,j,matrix.length,1);if(/title|rationale|transfer|question|notes|gap|query|basis|reason|judgment/.test(k)){range.format.columnWidth=62;range.format.wrapText=true;}if(/_id$/.test(k))range.format.columnWidth=16;if(/_url$/.test(k))range.format.columnWidth=45;if(/date/.test(k))sheet.getRangeByIndexes(1,j,Math.max(1,matrix.length-1),1).setNumberFormat('yyyy-mm-dd');}
}
const counts=input.counts,master=input.literature_master,heads=master[0],last=master.length,scol=col(heads.indexOf('screening_status')),tcol=col(heads.indexOf('method_relevance_tier'));
summary.showGridLines=false;summary.getRange('A1:F28').format.font.name='Arial';summary.getRange('A1:F28').format.font.size=10;summary.getRange('A1:F28').format.columnWidth=23;summary.getRange('A1:F28').format.rowHeight=30;summary.getRange('A1:F28').format.wrapText=true;summary.getRange('A2').values=[['LLM社会模拟方法研究']];summary.getRange('A2').format.font.size=15;summary.getRange('A2').format.font.bold=true;summary.getRange('A3').values=[['2022-01-01 至 2026-11-26']];
summary.getRange('A5:C5').values=[['文献状态','数量','解释']];summary.getRange('A6:C10').values=[['全部题录',counts.records,'含首轮保留及后续增补'],['全文确认纳入',null,'日期及主文核查门通过'],['候选',null,'部分已读，日期/筛选仍待核'],['前沿',null,'仅预印本，正式版分列'],['排除',null,'保留原排除依据']];
for(const [i,s]of ['included','candidate','frontier','excluded'].entries())summary.getRange(`B${7+i}`).formulas=[[`=COUNTIF('文献与方法编码'!$${scol}$2:$${scol}$${last},"${s}")`]];
summary.getRange('A13:C13').values=[['方法首要功能','全部记录','全文确认']];
for(const [i,t]of ['core_method','method_validation','application','direct_comparator','peripheral'].entries()){
const row=i+14;summary.getRange(`A${row}`).values=[[t]];summary.getRange(`B${row}`).formulas=[[`=COUNTIF('文献与方法编码'!$${tcol}$2:$${tcol}$${last},"${t}")`]];summary.getRange(`C${row}`).formulas=[[`=COUNTIFS('文献与方法编码'!$${tcol}$2:$${tcol}$${last},"${t}",'文献与方法编码'!$${scol}$2:$${scol}$${last},"included")`]];}
summary.getRange('A21:C24').values=[['本轮重点','证据规则','状态入口'],['方法范式、校准验证、复现','未全文者成熟度/证据待核','GOAL.md与progress.md'],['发表生态与双轨策略','先例与当前投稿适配分开','方法发表地图与双轨投稿'],['第一轮成果','原57条/15卡/导出保留','首轮期刊覆盖状态不改变']];
for(const range of ['A5:C5','A13:C13','A21:C21']){summary.getRange(range).format.fill='#263A5F';summary.getRange(range).format.font.color='#FFFFFF';summary.getRange(range).format.font.bold=true;}
summary.getRange('A1:A28').format.columnWidth=38;summary.getRange('B1:B28').format.columnWidth=36;summary.getRange('C1:C28').format.columnWidth=44;
wb.recalculate();await wb.inspect({kind:'region',sheetId:'方法研究进度',range:'A5:C24',maxChars:1800});const file=await SpreadsheetFile.exportXlsx(wb);await file.save(path.join(root,'exports/literature_and_journals_methods.xlsx'));
const png=await wb.render({sheetName:'方法研究进度',range:'A2:C24',format:'png',scale:1.25});await fs.writeFile(path.join(path.dirname(process.argv[1]),'methods_preview.png'),new Uint8Array(await png.arrayBuffer()));console.log(JSON.stringify({records:counts.records,output:'literature_and_journals_methods.xlsx'}));
