/** Inclusive overlap queries; restore original order for stable evidence identity. */
export function intervals(values,bounds) {
 const rows=values.map((value,index)=>({value,index,range:bounds(value)}))
  .filter(r=>!Number.isNaN(r.range[0])&&!Number.isNaN(r.range[1]))
  .sort((a,b)=>a.range[0]-b.range[0]||a.index-b.index);
 let maximum=-Infinity;
 const prefix=rows.map(r=>(maximum=Math.max(maximum,r.range[1])));
 return (lo,hi)=>{
  let left=0,right=rows.length;
  while(left<right){const middle=(left+right)>>>1;if(rows[middle].range[0]<=hi)left=middle+1;else right=middle;}
  const found=[];
  for(let i=left-1;i>=0&&prefix[i]>=lo;i--)if(rows[i].range[1]>=lo)found.push(rows[i]);
  return found.sort((a,b)=>a.index-b.index).map(r=>r.value);
 };
}
export function lanes(values,bounds) {
 const groups=new Map();
 for(const value of values){if(!groups.has(value.lane))groups.set(value.lane,[]);groups.get(value.lane).push(value);}
 const indexes=new Map([...groups].map(([lane,items])=>[lane,intervals(items,bounds)]));
 return (lane,lo,hi)=>indexes.get(lane)?.(lo,hi)??[];
}
