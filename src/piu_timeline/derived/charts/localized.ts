/** Join official localized titles to current UCS identities without fuzzy matching. */
import type {RecordData} from '../types.ts';

export const key=(title:string)=>title.normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]/gu,'');

function variant(title:string,type:string):string {
 const suffix=type==='FULL'?' - FULL SONG -':type==='SHORT'?' - SHORT CUT -':'';
 return suffix&&!key(title).endsWith(key(suffix))?title+suffix:title;
}

export function associate(songs:RecordData[],rows:RecordData[],existing:RecordData,source:RecordData):RecordData {
 const titles=new Map<string,Set<string>>(),proposed=new Map<string,RecordData[]>(),unresolved=[];
 for(const song of songs){
  const title=key(song.title);
  if(!titles.has(title))titles.set(title,new Set());
  titles.get(title).add(song.index);
 }
 for(const row of rows){
  const title=variant(row.title,row.type),localized=variant(row.localized_title,row.type);
  const codes=titles.get(key(title));
  if(codes?.size!==1){unresolved.push({...row,reason:codes?.size?'ambiguous_official_title':'official_title_not_in_ucs_catalogue'});continue;}
  const name=key(localized),entry={title:localized,index:[...codes][0],basis:'official_localized_catalogue',
   official_title:title,source_url:source.url,pdf_sha256:source.sha256,page:row.page};
  if(!proposed.has(name))proposed.set(name,[]);
  proposed.get(name).push(entry);
 }
 const aliases={...existing},conflicts=[];
 for(const [name,entries]of proposed){
  const codes=new Set(entries.map(e=>e.index));
  const direct=titles.get(name);
  if(codes.size!==1||(direct&&[...direct].some(code=>!codes.has(code)))||
    (existing[name]&&!codes.has(existing[name].index))){
   conflicts.push({key:name,candidates:entries,existing:existing[name]??null});continue;
  }
  if(!existing[name])aliases[name]=entries[0];
 }
 return {aliases,added:Object.keys(aliases).length-Object.keys(existing).length,conflicts,unresolved};
}
