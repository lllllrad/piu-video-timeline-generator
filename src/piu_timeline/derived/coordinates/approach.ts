/** The same measured approach coordinates feed registration and endpoint clocks. */
import type {RecordData} from '../types.ts';
export const qualifiedCap=(track:RecordData):boolean=>track.coordinate_basis==='native_cap_center'&&
 Number.isFinite(track.registration_uncertainty_pixels)&&track.registration_uncertainty_pixels>0;
export function approachPoints(track:RecordData,receptor:number,spacing:number,bottom:number):number[][]{
 const ordinary=track.points.filter(([,y])=>receptor+.85*spacing<y&&y<bottom-.55*spacing);
 if(ordinary.length>=2||!qualifiedCap(track))return ordinary;
 return track.points.filter(([,y])=>receptor+track.registration_uncertainty_pixels<y&&y<bottom-.55*spacing);
}
