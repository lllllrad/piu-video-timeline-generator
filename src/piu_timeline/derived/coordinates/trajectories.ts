/** Coordinate origins must agree before a distance can constrain another track. */
import {equal} from '../math.ts';
import {imagePosition, sameBasis, type CoordinateBasis} from './measurements.ts';
import {fitTrajectory} from './points.ts';
import type {Note, RecordData} from '../types.ts';

export class TrajectoryCoordinates {
  records:Map<number,RecordData>;
  timeline:Map<number,number>;
  cache=new Map<number,CoordinateBasis>();
  notes:Note[];
  registration:RecordData;
  constructor(notes:Note[],registration:RecordData,motion:RecordData){
    this.notes=notes;this.registration=registration;
    this.records=new Map((registration?.notes??[]).map(r=>[r.note,r]));
    this.timeline=new Map((motion?.samples??[]).map(s=>[s.time,s.source_pts]));
  }
  basis(i:number):CoordinateBasis{
    if(this.cache.has(i))return this.cache.get(i);
    const result=this.measure(i);this.cache.set(i,result);return result;
  }
  private measure(i:number):CoordinateBasis{
    const r=this.records.get(i),unavailable=(reason:string):CoordinateBasis=>({kind:'unavailable',reason});
    if(r?.coordinate_method==='native_cap_measurements')return {kind:'native_cap_center'};
    if(r?.coordinate_method!=='native_image_anchors')return unavailable('missing_coordinate_registration');
    const observations=new Map<number,RecordData>(r.observations.map(o=>[o.time,o]));
    const points=fitTrajectory(this.notes[i]).points;
    if(observations.size!==r.observations.length||!points.length)return unavailable('invalid_measurement_timeline');
    const samples=points.map(([time,y])=>{
      const position=imagePosition(observations.get(time),y,this.registration.format);
      if(position.kind==='unavailable')return position;
      if(!Number.isFinite(this.timeline.get(time))||Math.abs(position.sourcePtsSeconds-this.timeline.get(time))>1e-6)
        return unavailable('source_pts_conflict');
      return position;
    });
    const bad=samples.find(s=>s.kind==='unavailable');
    if(bad?.kind==='unavailable')return bad;
    if(samples.every(s=>s.kind==='native_cap_center'||s.kind==='conflicting_center_projection'&&r.coordinate_status==='projected'))
      return {kind:'native_cap_center'};
    if(samples.every(s=>s.kind==='image_reference_anchor')){
      const reference=samples[0].reference;
      if(samples.every(s=>s.kind==='image_reference_anchor'&&equal(s.reference,reference)))return {kind:'image_reference_anchor',reference};
    }
    return unavailable('mixed_or_unregistered_coordinate_origins');
  }
  hasCapCenter(i:number):boolean{return this.basis(i).kind==='native_cap_center';}
  incompatible(a:number,b:number):number[]{
    const first=this.basis(a),second=this.basis(b);
    if(sameBasis(first,second))return [];
    return [a,b].filter(i=>!this.hasCapCenter(i));
  }
}
