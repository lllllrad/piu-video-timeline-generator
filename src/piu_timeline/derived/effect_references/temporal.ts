import type {Patch} from './model.ts';
export function evolution(query:Patch[],reference:Patch[]) {
 let total=0,count=0,change=0;
 for(let s=1;s<query.length;s++) {
  const a=query[s-1],b=query[s],c=reference[s-1],d=reference[s];if(!a||!b||!c||!d)continue;
  let support=0,error=0,motion=0;
  for(let i=0;i<1521;i++)if(a.visible[i]&&b.visible[i]&&c.visible[i]&&d.visible[i]) {
   support++;
   for(let k=0;k<3;k++) {
    const q=b.rgb[i*3+k]-a.rgb[i*3+k],r=d.rgb[i*3+k]-c.rgb[i*3+k];
    error+=Math.abs(q-r);motion+=Math.abs(r);
   }
  }
  if(support<1521*.65)continue;
  total+=error/(support*3*510);change+=motion/(support*3*255);count++;
 }
 return {error:count?total/count:null,comparisons:count,reference_change:count?change/count:0};
}
export function changes(patches:Patch[]) {
 const results=[];
 for(let i=1;i<patches.length;i++) {
  const a=patches[i-1],b=patches[i];let error=0,rise=0,count=0;
  if(b.frame.time-a.frame.time>.035)continue;
  for(let j=0;j<1521;j++)if(a.visible[j]&&b.visible[j]) {
   count++;for(let k=0;k<3;k++){const d=b.rgb[j*3+k]-a.rgb[j*3+k];error+=Math.abs(d);rise+=d;}
  }
  if(count<1521*.65)continue;
  const change=error/(count*3*255),brightening=rise/(count*3*255);
  if(change>=.025)results.push({bracket:[a.frame.time,b.frame.time],source_pts:[a.frame.pts,b.frame.pts],change,brightening});
 }
 return results.sort((a,b)=>b.change-a.change);
}
