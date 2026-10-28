/** Observable browser boundary shared by shipped-script integration tests. */
import assert from 'node:assert/strict';
export function createDOM(html: string, activeAnimations = new Set<any>()) {
  let createdNodes=0;
  function element(tag): Record<string, any> {
    createdNodes++;
    return {tag,style:{},attributes:{},children:[],textContent:'',value:'',hidden:false,
      clientWidth:1200,clientHeight:350,complete:false,files:[],paused:true,ended:false,currentTime:0,playbackRate:1,handlers:{},
      setAttribute(name,value){this.attributes[name]=String(value);if(['x','y','x1','y1','x2','y2','cx','cy','width','height','r'].includes(name))assert.ok(Number.isFinite(Number(value)),name+' has invalid geometry')},
      getAttribute(name){return this.attributes[name]??null},
      appendChild(node){node.parentElement=this;this.children.push(node);return node},
      replaceChildren(){this.children=[]},
      addEventListener(event,callback){(this.handlers[event]??=[]).push(callback)},
      getBoundingClientRect(){return {left:0,top:0,width:this.clientWidth,height:this.clientHeight}},
      closest(selector){if(selector==='[data-note]'&&this.getAttribute('data-note')!==null)return this;return this.parentElement?.closest(selector)??null},
      focus(){this.focused=true},
      animate(keyframes,options){const animation={currentTime:0,keyframes,options,cancel(){activeAnimations.delete(this)}};activeAnimations.add(animation);return animation},
      getContext(){throw Error('canvas rendering is forbidden')},
    };
  }
  const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(match=>match[1]);
  assert.equal(new Set(ids).size,ids.length,'every shipped DOM ID must be unique');
  const elements=new Map(ids.map(id=>[id,element(id)]));
  for(const match of html.matchAll(/<svg id="([^"]+)" viewBox="0 0 (\d+) (\d+)"/g)){
    const root=elements.get(match[1]);root.setAttribute('viewBox',`0 0 ${match[2]} ${match[3]}`);root.clientWidth=Number(match[2]);root.clientHeight=Number(match[3]);
  }
  for(const match of html.matchAll(/<[^>]*\bid="([^"]+)"[^>]*>/g)){
    const node=elements.get(match[1]);node.hidden=/\bhidden\b/.test(match[0]);node.checked=/\bchecked\b/.test(match[0]);
    const value=match[0].match(/\bvalue="([^"]*)"/);if(value)node.value=value[1];
  }
  elements.get('sourceOverlay').parentElement=element('source-stage');
  const document={getElementById(id){assert.ok(elements.has(id),'missing element '+id);return elements.get(id)},
    createElement:element,createElementNS(namespace,tag){assert.equal(namespace,'http://www.w3.org/2000/svg');return element(tag)}};
  return {elements,element,document,nodeCount:()=>createdNodes};
}
export const descendants=node=>node.children.flatMap(child=>[child,...descendants(child)]);
