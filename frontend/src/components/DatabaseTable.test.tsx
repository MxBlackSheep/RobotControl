import {expect,it,vi} from 'vitest';
import {collectMatchingRows,formatExport} from './databaseExport';

// Failure cases: truncated exports, changed row counts, cancellation ignored or invalid CSV.
it('exports more than 1000 matching rows in bounded pages and detects changes',async()=>{
 const fetch=vi.fn(async(page:number)=>({rows:Array.from({length:page===1?1000:205},(_,i)=>({id:(page-1)*1000+i})),total_count:1205}));
 const rows=await collectMatchingRows(fetch,new AbortController().signal,vi.fn());expect(rows).toHaveLength(1205);expect(fetch.mock.calls).toEqual([[1,1000],[2,1000]]);
 const changed=vi.fn().mockResolvedValueOnce({rows:[{id:1}],total_count:2}).mockResolvedValueOnce({rows:[],total_count:1});
 await expect(collectMatchingRows(changed,new AbortController().signal,vi.fn())).rejects.toThrow('changed');
 const abort=new AbortController();abort.abort();await expect(collectMatchingRows(fetch,abort.signal,vi.fn())).rejects.toThrow('cancelled');
 expect(formatExport(['name'],[{name:'a,"b"'}],'csv')).toContain('"a,""b"""');
});
