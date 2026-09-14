export async function collectMatchingRows(fetchPage:(page:number,limit:number)=>Promise<{rows:Record<string,any>[];total_count:number}>, signal:AbortSignal, progress:(count:number)=>void) {
  const rows:Record<string,any>[]=[]; let total:number|undefined; let bytes=0;
  for(let page=1;total===undefined || rows.length<total;page++) {
    if(signal.aborted)throw new Error('Export cancelled.');
    const batch=await fetchPage(page,1000);
    if(signal.aborted)throw new Error('Export cancelled.');
    if(total!==undefined && total!==batch.total_count)throw new Error('Matching row count changed during export. Please retry when the table is stable.');
    total=batch.total_count;
    if(!batch.rows.length && rows.length<total)throw new Error('Export ended before all matching rows were returned. No file was downloaded.');
    bytes+=new Blob([JSON.stringify(batch.rows)]).size;
    if(bytes>50*1024*1024)throw new Error('Export exceeds 50 MB. Narrow the search or filters and retry.');
    rows.push(...batch.rows);progress(rows.length);
  }
  return rows;
}
export function formatExport(columns:string[], rows:Record<string,any>[], format:'csv'|'json') {
  if(format==='json')return JSON.stringify(rows.map(row=>Object.fromEntries(columns.map(c=>[c,row[c]]))),null,2);
  const cell=(value:any)=>'"'+String(value??'').replace(/"/g,'""')+'"';
  return [columns.map(cell).join(','),...rows.map(row=>columns.map(c=>cell(row[c])).join(','))].join('\r\n');
}
