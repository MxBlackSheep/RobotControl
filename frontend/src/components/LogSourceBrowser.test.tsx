import React from 'react';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import LogSourceBrowser from './LogSourceBrowser';
import {logFileApi} from '../services/logFileApi';
vi.mock('../services/logFileApi',()=>({logFileApi:{browse:vi.fn(),browseArchive:vi.fn(),preview:vi.fn(),previewArchive:vi.fn()}}));
const source={id:'python_log',label:'Python logs',path:'C:/logs',exists:true,accessible:true};
const listing={items:[{name:'run.log',path:'C:/logs/run.log',is_directory:false,extension:'.log'},{name:'other.log',path:'C:/logs/other.log',is_directory:false,extension:'.log'},{name:'nested',is_directory:true}],total_items:251};
const preview={content:'first line\nsecond line',bytes_returned:22,is_binary:false,mode:'tail'};
beforeEach(()=>{vi.mocked(logFileApi.browse).mockResolvedValue(listing as any);vi.mocked(logFileApi.preview).mockResolvedValue(preview as any);});
afterEach(()=>vi.useRealTimers());
it('searches filenames before paging and keeps old results on a failed refresh',async()=>{
 render(<LogSourceBrowser source={source} active/>);await screen.findByText('run.log');
 expect(vi.mocked(logFileApi.browse).mock.calls[0][2]).toMatchObject({page:1,limit:50});
 fireEvent.change(screen.getByLabelText('Find filenames in this folder'),{target:{value:'old'}});expect(logFileApi.browse).toHaveBeenCalledTimes(1);
 fireEvent.click(screen.getByRole('button',{name:'Search',exact:true}));await waitFor(()=>expect(logFileApi.browse).toHaveBeenCalledTimes(2));expect(vi.mocked(logFileApi.browse).mock.calls[1][2]).toMatchObject({search:'old',page:1});
 vi.mocked(logFileApi.browse).mockRejectedValueOnce(new Error('Folder locked'));fireEvent.click(screen.getByRole('button',{name:'Refresh files'}));await screen.findByText(/Folder locked/);expect(screen.getByText('run.log')).toBeTruthy();
});
it('separates file refresh from preview refresh and ignores an old file response',async()=>{
 let resolve:any;vi.mocked(logFileApi.preview).mockImplementationOnce(()=>new Promise(r=>{resolve=r;}));
 render(<LogSourceBrowser source={source} active/>);await screen.findByText('run.log');fireEvent.click(screen.getByText('run.log'));fireEvent.click(screen.getByText('other.log'));await screen.findByText(/first line/);
 await act(async()=>resolve({...preview,content:'stale wrong file'}));expect(screen.queryByText('stale wrong file')).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Refresh files'}));await waitFor(()=>expect(logFileApi.browse).toHaveBeenCalledTimes(2));expect(logFileApi.preview).toHaveBeenCalledTimes(2);
 fireEvent.click(screen.getByRole('button',{name:'Refresh preview'}));await waitFor(()=>expect(logFileApi.preview).toHaveBeenCalledTimes(3));
});
it('preserves preview on failure, clears it after successful folder navigation',async()=>{
 render(<LogSourceBrowser source={source} active/>);await screen.findByText('run.log');fireEvent.click(screen.getByText('run.log'));await screen.findByText(/first line/);
 vi.mocked(logFileApi.preview).mockRejectedValueOnce(new Error('File missing'));fireEvent.click(screen.getByRole('button',{name:'Refresh preview'}));await screen.findByText(/File missing/);expect(screen.getByText(/first line/)).toBeTruthy();
 fireEvent.click(screen.getByText('▸ nested'));await waitFor(()=>expect(screen.queryByText(/first line/)).toBeNull());
});
it('follows without overlapping requests and stops when hidden',async()=>{
 const view=render(<LogSourceBrowser source={source} active/>);await screen.findByText('run.log');fireEvent.click(screen.getByText('run.log'));await screen.findByText(/first line/);
 fireEvent.click(screen.getByRole('button',{name:'Reading tools'}));vi.useFakeTimers();let resolve:any;vi.mocked(logFileApi.preview).mockImplementationOnce(()=>new Promise(r=>{resolve=r;}));fireEvent.click(screen.getByLabelText('Follow latest (5s)'));
 await act(async()=>{await vi.advanceTimersByTimeAsync(15000);});expect(logFileApi.preview).toHaveBeenCalledTimes(2);
 await act(async()=>resolve(preview));await act(async()=>{await vi.advanceTimersByTimeAsync(5000);});expect(logFileApi.preview).toHaveBeenCalledTimes(3);
 view.rerender(<LogSourceBrowser source={source} active={false}/>);await act(async()=>{await vi.advanceTimersByTimeAsync(15000);});expect(logFileApi.preview).toHaveBeenCalledTimes(3);
});
it('limits Find to preview text and lets Escape close expanded preview',async()=>{
 render(<LogSourceBrowser source={source} active/>);await screen.findByText('run.log');fireEvent.click(screen.getByText('run.log'));await screen.findByText(/first line/);
 fireEvent.click(screen.getByRole('button',{name:'Reading tools'}));fireEvent.change(screen.getByLabelText('Find in preview'),{target:{value:'line'}});expect(screen.getByText('2 matches in shown text only')).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'Expand preview'}));expect(screen.getByRole('dialog',{name:'Expanded log preview'})).toBeTruthy();fireEvent.keyDown(screen.getByRole('dialog'),{key:'Escape'});await waitFor(()=>expect(screen.queryByRole('dialog')).toBeNull());
});
