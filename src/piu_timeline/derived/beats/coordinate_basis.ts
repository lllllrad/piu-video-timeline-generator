/** Coordinate origins must agree before a distance can constrain another track. */
import {contracts} from '../contracts.ts';
import {equal} from '../math.ts';
import type {Note, RecordData} from '../types.ts';
const CENTER='native_cap_center', EPS=1e-8;

export class CoordinateBases {
  records:Map<number,RecordData>;
  timeline:Map<number,number>;
  cache=new Map<number,string|null>();
  notes:Note[];
  registration:RecordData;
  constructor(notes:Note[],registration:RecordData,motion:RecordData){
    this.notes=notes;this.registration=registration;
    this.records=new Map((registration?.notes??[]).map(r=>[r.note,r]));
    this.timeline=new Map((motion?.samples??[]).map(s=>[s.time,s.source_pts]));
  }
  basis(i:number):string|null{
    if(this.cache.has(i))return this.cache.get(i);
    const result=this.measure(i);this.cache.set(i,result);return result;
  }
  private measure(i:number):string|null{
    const r=this.records.get(i);
    // Native silhouette registrations predate the explicit method field.
    if(r&&(!r.coordinate_method||r.coordinate_method==='native_cap_measurements'))return CENTER;
    if(r?.coordinate_method!=='native_image_anchors')return null;
    const observations=new Map<number,RecordData>(r.observations.map(o=>[o.time,o]));
    if(observations.size!==r.observations.length||!this.notes[i].points.length)return null;
    const samples=this.notes[i].points.map(([time,y])=>{
      const o=observations.get(time);
      if(!o||!Number.isFinite(o.native_y_pixels)||Math.abs(o.native_y_pixels-y)>EPS||
        !Number.isFinite(o.source_pts_seconds)||!Number.isFinite(this.timeline.get(time))||Math.abs(o.source_pts_seconds-this.timeline.get(time))>1e-6)return null;
      return o;
    });
    if(samples.some(o=>!o))return null;
    if(equal(this.registration.format?.native_cap_registration,contracts.native_anchor)&&samples.every(o=>{
      const e=o.native_cap_coordinate_uncertainty_pixels,s=o.native_cap_reference_scale_y;
      if(typeof s!=='number'||!Number.isFinite(s)||s<=0)return false;
      const bound=s*contracts.native_anchor.coordinate_uncertainty_pixels;
      if(o.native_cap_registration_status==='conflicting'){
        const projected=o.native_cap_projection_uncertainty_pixels;
        return r.coordinate_status==='projected'&&typeof projected==='number'&&Number.isFinite(projected)&&projected>=bound&&
          typeof o.native_cap_reference_template==='string';
      }
      return typeof e==='number'&&Number.isFinite(e)&&e>0&&Math.abs(e-bound)<EPS;
    }))return CENTER;
    // Only one identical reference can cancel an uncalibrated matching origin.
    const identities=samples.map(o=>o.cap_reference_sha256?`reference:${o.cap_reference_sha256}`:o.template?`template:${o.template}`:null);
    return identities[0]&&identities.every(id=>id===identities[0])?identities[0]:null;
  }
  calibrated(i:number):boolean{return this.basis(i)===CENTER;}
  incompatible(a:number,b:number):number[]{
    const first=this.basis(a),second=this.basis(b);
    if(first&&first===second)return [];
    return [a,b].filter(i=>!this.calibrated(i));
  }
}
