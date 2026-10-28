/** Recover uniquely corroborated native identities before estimating musical rows. */
import {contracts} from './contracts.ts';
import {linear, median, rms, upperBound} from './math.ts';
import {fit as fitClock} from './clocks.ts';
import {fitTrack} from './tracks.ts';
import type {RecordData} from './types.ts';
const F=contracts.fragments;
type Result = [RecordData[], number[][]];
const lanes = (tracks: RecordData[]) => {
  const result = new Map<number, number[]>();
  tracks.forEach((t,i) => { if (!result.has(t.lane)) result.set(t.lane, []); result.get(t.lane).push(i); });
  return result;
};
const joined = (a: RecordData, b: RecordData) => ({lane:a.lane, points:[...a.points,...b.points].sort((x,y)=>x[0]-y[0]),
  ...((a.fragment_connections?.length||b.fragment_connections?.length)?{fragment_connections:[...(a.fragment_connections??[]),...(b.fragment_connections??[])]}:{})});

export function interleaved(tracks: RecordData[], spacing: number, motion: RecordData | null): Result {
  const origins=tracks.map((_,i)=>[i]);
  if (motion?.evidence_format?.method!=='registered_peer_displacement') return [tracks,origins];
  const at=new Map<number,RecordData>((motion.samples??[]).map(s=>[s.time,s])), outgoing=new Map<number,number[]>(), incoming=new Map<number,number[]>();
  const link=(map,key,value)=>{if(!map.has(key))map.set(key,[]);map.get(key).push(value);};
  for(const indices of lanes(tracks).values()){
    const ordered=indices.filter(i=>tracks[i].points.length>=4).sort((a,b)=>tracks[a].points[0][0]-tracks[b].points[0][0]);
    ordered.forEach((a,pos)=>{
      const first=tracks[a],start=first.points[0][0],end=first.points.at(-1)[0];
      for(const b of ordered.slice(pos+1)){
        const second=tracks[b],begin=second.points[0][0],stop=second.points.at(-1)[0];
        if(begin>=end)break;
        if(!(start<begin&&begin<end&&end<stop)||end-begin>.1+1e-6)continue;
        const times=new Set(first.points.map(p=>p[0]));if(second.points.some(p=>times.has(p[0])))continue;
        const anchor=at.get(begin);if(!anchor||Object.hasOwn(motion.coordinate_failures??{},anchor.chunk))continue;
        const offsets=[];
        for(const track of [first,second]){
          const points=track.points.filter(([t])=>at.get(t)?.chunk===anchor.chunk);
          if(points.length<4||points.at(-1)[0]-points[0][0]<.065)break;
          const values=points.map(([t,y])=>y+at.get(t).phase),center=median(values);
          if(Math.max(...values.map(v=>Math.abs(v-center)))>F.maximum_reference_error_spacing*spacing)break;
          offsets.push(center);
        }
        if(offsets.length===2&&Math.abs(offsets[0]-offsets[1])<=F.maximum_continuation_error_spacing*spacing){link(outgoing,a,b);link(incoming,b,a);}
      }
    });
  }
  const pairs=new Map<number,number[]>();
  for(const [i,owners]of outgoing)if(owners.length===1&&incoming.get(owners[0]).length===1){
    const other=owners[0];if(!outgoing.has(other)&&!incoming.has(i))pairs.set(Math.min(i,other),[i,other]);
  }
  const used=new Set<number>(),result=[],sources=[];
  tracks.forEach((track,i)=>{
    if(used.has(i))return;
    const pair=pairs.get(i);
    if(pair){result.push(joined(tracks[pair[0]],tracks[pair[1]]));sources.push(pair);pair.forEach(j=>used.add(j));}
    else{result.push(track);sources.push([i]);}
  });
  return [result,sources];
}

/** A native displacement origin must use the intact approach, not one endpoint. */
function anchor(points: number[][], at: Map<number,RecordData>, spacing: number, motion: RecordData | null): RecordData {
  const chunk=at.get(points.at(-1)[0])?.chunk;
  if(motion?.evidence_format?.method!=='registered_peer_displacement'||chunk==null||
    Object.hasOwn(motion.coordinate_failures??{},chunk)||points.some(([t])=>at.get(t)?.chunk!==chunk)||
    points.length<F.minimum_references||points.at(-1)[0]-points[0][0]<F.minimum_span_seconds)return {status:'unavailable'};
  const offsets=points.map(([t,y])=>y+at.get(t).phase),error=F.maximum_reference_error_spacing*spacing;
  const range=[Math.max(...offsets.map(v=>v-error)),Math.min(...offsets.map(v=>v+error))];
  return {status:range[0]<=range[1]?'fitted':'conflicting',chunk,range,references:points.map(([t,y])=>({time:t,y,phase:at.get(t).phase,source_pts_seconds:at.get(t).source_pts}))};
}

export function stitch(source: RecordData[], receptor: number, spacing: number, motion: RecordData | null = null, layout: RecordData | null = null): Result {
  const [tracks,origins]=interleaved(source,spacing,motion),at=new Map<number,RecordData>((motion?.samples??[]).map(s=>[s.time,s]));
  const candidates=new Map<number,{successor:number;track:RecordData}[]>(),incoming=new Map<number,number[]>();
  for(const indices of lanes(tracks).values()){
    const ordered=[...indices].sort((a,b)=>tracks[a].points[0][0]-tracks[b].points[0][0]),starts=ordered.map(i=>tracks[i].points[0][0]);
    for(const index of indices){
      const track=tracks[index];if(track.points.length<3)continue;
      let usable=track.points;
      if(layout?.combo_roi){
        const [x,y,w,h]=layout.combo_roi,height=receptor/layout.receptor_y,laneX=layout.lanes[track.lane].x;
        if(x-.12<=laneX&&laneX<=x+w+.12&&track.points.at(-1)[1]<=(y+h)*height+spacing)
          usable=track.points.filter(p=>(y+h)*height+spacing<p[1]&&p[1]<(layout.note_y_max??.95)*height-.55*spacing);
      }
      if(usable.length<4)continue;
      const points=usable.slice(-12),origin=points.at(-1)[0],times=points.map(p=>p[0]-origin);
      if(times[0]>-.06)continue;
      const [velocity,intercept]=linear(times,points.map(p=>p[1])),residual=rms(points.map((p,i)=>p[1]-velocity*times[i]-intercept));
      if(velocity>=-spacing||residual>.1*spacing)continue;
      const registered=anchor(points,at,spacing,motion);if(registered.status==='conflicting')continue;
      const first=upperBound(starts,track.points.at(-1)[0]),last=upperBound(starts,track.points.at(-1)[0]+.35);
      for(const successor of ordered.slice(first,last)){
        const other=tracks[successor];if(other.points.length<2||other.points[0][0]-origin>.65)continue;
        const prediction=time=>{
          const a=at.get(origin),b=at.get(time);
          const valid=a&&b&&a.chunk===b.chunk&&!Object.hasOwn(motion?.coordinate_failures??{},a.chunk);
          return valid?points.at(-1)[1]-(b.phase-a.phase):intercept+velocity*(time-origin);
        };
        const initial=other.points.slice(0,3),error=F.maximum_continuation_error_spacing*spacing;
        let connection:RecordData|null=null;
        if(registered.status==='fitted'&&initial.every(([t])=>at.get(t)?.chunk===registered.chunk)){
          // One common anchor must explain every reference and reappearance.
          const offsets=initial.map(([t,y])=>y+at.get(t).phase);
          const lower=Math.max(registered.range[0],...offsets.map(v=>v-error));
          const upper=Math.min(registered.range[1],...offsets.map(v=>v+error));
          if(lower>upper)continue;
          connection={format:F,method:'joint_registered_native_bands',chunk:registered.chunk,lane_spacing_pixels:spacing,
            predecessor_end_seconds:tracks[index].points.at(-1)[0],successor_start_seconds:other.points[0][0],
            reference_error_pixels:F.maximum_reference_error_spacing*spacing,continuation_error_pixels:error,
            reference_offset_range_pixels:registered.range,common_offset_range_pixels:[lower,upper],
            references:registered.references,reappearances:initial.map(([t,y])=>({time:t,y,phase:at.get(t).phase,source_pts_seconds:at.get(t).source_pts}))};
        }else if(initial.some(([t,y])=>Math.abs(y-prediction(t))>error))continue;
        const track=joined(tracks[index],other),fit=(motion?fitClock(motion,track,receptor,layout):null)??fitTrack(track,receptor,spacing);
        if(fit.status!=='estimated')continue;
        if(connection)track.fragment_connections=[...(track.fragment_connections??[]),connection];
        if(!candidates.has(index))candidates.set(index,[]);candidates.get(index).push({successor,track});
        if(!incoming.has(successor))incoming.set(successor,[]);incoming.get(successor).push(index);
      }
    }
  }
  const used=new Set<number>(),result=[],sources=[];
  tracks.forEach((track,index)=>{
    if(used.has(index))return;
    const links=candidates.get(index)??[];
    if(links.length===1){
      const link=links[0],successor=link.successor;
      if(incoming.get(successor).length===1&&!used.has(successor)&&successor>index){
        used.add(successor);result.push(link.track);sources.push([...origins[index],...origins[successor]]);return;
      }
    }
    result.push(track);sources.push(origins[index]);
  });
  return [result,sources];
}
