/** Clip a convex feasible region by one closed linear half-plane. */
export type Vertex=[number,number];
export function clipPlane(vertices:Vertex[],score:(point:Vertex)=>number):Vertex[]{
 const result:Vertex[]=[];
 for(let i=0;i<vertices.length;i++){
  const a=vertices[i],b=vertices[(i+1)%vertices.length],fa=score(a),fb=score(b);
  if(fa>=-1e-9)result.push(a);
  if((fa>=-1e-9)!==(fb>=-1e-9)){
   const fraction=fa/(fa-fb);result.push([a[0]+fraction*(b[0]-a[0]),a[1]+fraction*(b[1]-a[1])]);
  }
 }
 return result;
}
