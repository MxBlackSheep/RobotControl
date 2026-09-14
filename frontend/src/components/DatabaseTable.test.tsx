import React from 'react';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import DatabaseTable from './DatabaseTable';
import {collectMatchingRows,formatExport} from './databaseExport';
import {databaseAPI} from '../services/api';
vi.mock('../services/api',()=>({databaseAPI:{getTableData:vi.fn()}}));
const response=(name='first')=>({data:{data:{columns:['id','name'],rows:[{id:1,name}],total_count:1}}});
beforeEach(()=>vi.mocked(databaseAPI.getTableData).mockResolvedValue(response() as any));
it('applies search only on submit and sends both sort directions',async()=>{
 render(<DatabaseTable tableName="Samples"/>);await screen.findByText('first');
 fireEvent.change(screen.getByLabelText('Search all supported columns'),{target:{value:'needle'}});
 expect(databaseAPI.getTableData).toHaveBeenCalledTimes(1);
 fireEvent.click(screen.getByRole('button',{name:'Apply'}));await waitFor(()=>expect(databaseAPI.getTableData).toHaveBeenCalledTimes(2));
 expect(vi.mocked(databaseAPI.getTableData).mock.calls[1][3]).toMatchObject({search:'needle'});
 fireEvent.click(screen.getByText('name'));await waitFor(()=>expect(databaseAPI.getTableData).toHaveBeenCalledTimes(3));
 fireEvent.click(screen.getByText('name'));await waitFor(()=>expect(databaseAPI.getTableData).toHaveBeenCalledTimes(4));
 expect(vi.mocked(databaseAPI.getTableData).mock.calls[3][3]).toMatchObject({order_by:'name',sort_direction:'desc'});
});
it('retains rows and input on refresh and ignores a response from an old table',async()=>{
 const view=render(<DatabaseTable tableName="A"/>);await screen.findByText('first');
 let resolve:any;vi.mocked(databaseAPI.getTableData).mockImplementationOnce(()=>new Promise(r=>{resolve=r;}));
 fireEvent.change(screen.getByLabelText('Search all supported columns'),{target:{value:'draft'}});fireEvent.click(screen.getByRole('button',{name:'Refresh'}));
 expect(screen.getByText('first')).toBeTruthy();expect(screen.getByDisplayValue('draft')).toBeTruthy();
 vi.mocked(databaseAPI.getTableData).mockResolvedValue(response('new table') as any);view.rerender(<DatabaseTable tableName="B"/>);await screen.findByText('new table');
 await act(async()=>resolve(response('stale')));expect(screen.queryByText('stale')).toBeNull();
});
it('distinguishes null and empty cells and opens complete values by button',async()=>{
 vi.mocked(databaseAPI.getTableData).mockResolvedValue({data:{data:{columns:['null','empty'],rows:[{null:null,empty:''}],total_count:1}}} as any);
 render(<DatabaseTable tableName="Values"/>);await screen.findByText('NULL');expect(screen.getByText('(empty string)')).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'View empty, row 1'}));expect(screen.getByRole('dialog')).toBeTruthy();
});
it('exports more than 1000 matching rows in bounded pages and detects changes',async()=>{
 const fetch=vi.fn(async(page:number)=>({rows:Array.from({length:page===1?1000:205},(_,i)=>({id:(page-1)*1000+i})),total_count:1205}));
 const rows=await collectMatchingRows(fetch,new AbortController().signal,vi.fn());expect(rows).toHaveLength(1205);expect(fetch.mock.calls).toEqual([[1,1000],[2,1000]]);
 const changed=vi.fn().mockResolvedValueOnce({rows:[{id:1}],total_count:2}).mockResolvedValueOnce({rows:[],total_count:1});
 await expect(collectMatchingRows(changed,new AbortController().signal,vi.fn())).rejects.toThrow('changed');
 const abort=new AbortController();abort.abort();await expect(collectMatchingRows(fetch,abort.signal,vi.fn())).rejects.toThrow('cancelled');
 expect(formatExport(['name'],[{name:'a,"b"'}],'csv')).toContain('"a,""b"""');
});
