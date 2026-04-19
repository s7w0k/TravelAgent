import re
from typing import Any, Dict, List, Optional
from backend.config import get_settings
from backend.logger import get_logger
from backend.rag.document_processor import get_document_processor
from backend.rag.keyword_retriever import get_keyword_retriever
from backend.rag.vector_store import get_vector_store
logger=get_logger(__name__)
settings=get_settings()

class SearchResult:
    def __init__(self,content:str,source:str,title:str,distance:float=0.0,metadata:dict=None):
        self.content=content;self.source=source;self.title=title;self.distance=distance;self.metadata=metadata or {}
    def __repr__(self):
        return f"<SearchResult source={self.source} title={self.title} distance={self.distance:.4f}>"

class Retriever:
    CA={"魔都":"上海","帝都":"北京","姑苏":"苏州","鹏城":"深圳","羊城":"广州"}
    TR={"遛娃":"亲子","带娃":"亲子","学生党":"学生","约会":"情侣","打卡":"攻略"}
    CS={"上海","北京","苏州","深圳","广州","杭州","南京","成都","重庆","西安","武汉","长沙","青岛","厦门"}
    PS={"亲子","情侣","学生","长者","老人"}
    SS={"春季","夏季","秋季","冬季","暑假","寒假","十一"}
    CN={"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10,"两":2}
    def __init__(self):
        self.document_processor=get_document_processor();self.vector_store=get_vector_store();self.keyword_retriever=get_keyword_retriever()
    async def add_document(self,content:str,title:str,source:str="全网",metadata:Optional[dict]=None)->bool:
        try:
            d=self.document_processor.process_document(content=content,title=title,source=source,metadata=metadata)
            return await self.vector_store.add_documents([c.content for c in d.chunks],[c.metadata for c in d.chunks],[c.chunk_id for c in d.chunks])
        except Exception as e:
            logger.error(f"添加文档失败: {e}");return False
    def _f(self,sources): return None if not sources else {"source":{"$in":sources}}
    def _vs(self,d):
        try:return max(0.0,min(1.0,1-float(d)))
        except Exception:return 0.0
    def _n(self,t): return re.sub(r"\s+","",(t or "").lower())
    def _k(self,c,t,m,f=""):
        x=m.get("chunk_id") or m.get("id") or f
        if x:return f"chunk:{x}"
        d,i=m.get("doc_id"),m.get("chunk_index")
        if d is not None and i is not None:return f"doc:{d}:{i}"
        return f"text:{self._n(t)}:{self._n(c)[:120]}"
    def _cons(self,q):
        r={"city":None,"days":None,"budget_max":None,"persona":None,"season":None}
        for a,c in self.CA.items():
            if a in q:r["city"]=c;break
        if not r["city"]:
            for c in self.CS:
                if c in q:r["city"]=c;break
        m=re.search(r"(\d+)\s*(?:天|日游)",q);r["days"]=int(m.group(1)) if m else None
        if r["days"] is None:
            for a,b in self.CN.items():
                if f"{a}日游" in q or f"{a}天" in q:r["days"]=b;break
        m=re.search(r"(?:预算|人均)?\s*(\d{3,6})\s*(?:元|块|以内|以下)?",q);r["budget_max"]=int(m.group(1)) if m else None
        for p in self.PS:
            if p in q:r["persona"]="长者" if p in {"老人","长者"} else p;break
        for s in self.SS:
            if s in q:r["season"]=s;break
        m=re.search(r"(1[0-2]|[1-9])月",q)
        if m and not r["season"]:r["season"]=f"{m.group(1)}月"
        return r
    def _rw(self,q,c):
        xs=[q]
        if settings.RAG_ENABLE_QUERY_REWRITE:
            r=q
            for a,b in self.CA.items(): r=r.replace(a,b)
            for a,b in self.TR.items(): r=r.replace(a,b)
            if r!=q: xs.append(r)
            if c.get("city"): xs.append(f"{c['city']} {r}")
        out=[]
        for x in xs:
            if x and x not in out: out.append(x)
        return out[:4]
    def _iv(self,v):
        if v is None or isinstance(v,bool):return None
        if isinstance(v,(int,float)):return int(v)
        m=re.search(r"\d+",str(v));return int(m.group()) if m else None
    def _mv(self,m,ks):
        for k in ks:
            v=m.get(k)
            if v not in (None,""): return v
        return None
    def _cand(self,c,s,t,d,m,vs,ks,rq):
        hs=vs*settings.RAG_VECTOR_WEIGHT+ks*settings.RAG_KEYWORD_WEIGHT
        rt="hybrid" if vs>0 and ks>0 else ("vector" if vs>0 else "keyword")
        return {"content":c,"source":s,"title":t,"distance":d,"metadata":m,"vector_score":vs,"keyword_score":ks,"hybrid_score":hs,"rewrite_query":rq,"retrieval_type":rt}
    def _merge(self,vr,kr,rq):
        md={};mk=max((i.score for i in kr),default=0.0)
        for i in vr:
            m=dict(i.get("metadata",{}) or {})
            if i.get("id") and "chunk_id" not in m:m["chunk_id"]=i["id"]
            k=self._k(i.get("content",""),m.get("title",""),m,i.get("id",""))
            md[k]=self._cand(i.get("content",""),m.get("source","未知"),m.get("title",""),i.get("distance",1.0),m,self._vs(i.get("distance",1.0)),0.0,rq)
        for i in kr:
            m=dict(i.metadata or {});m.setdefault("chunk_id",i.chunk_id);m.setdefault("doc_id",i.doc_id);m.setdefault("chunk_index",i.chunk_index);m.setdefault("title",i.title);m.setdefault("source",i.source)
            k=self._k(i.content,i.title,m,i.chunk_id);ks=i.score/mk if mk>0 else 0.0
            if k not in md: md[k]=self._cand(i.content,i.source,i.title,1.0,m,0.0,ks,rq)
            else:
                md[k]["keyword_score"]=max(md[k]["keyword_score"],ks)
                md[k]["hybrid_score"]=md[k]["vector_score"]*settings.RAG_VECTOR_WEIGHT+md[k]["keyword_score"]*settings.RAG_KEYWORD_WEIGHT
        return list(md.values())
    async def _vr(self,q,k,s=None): return await self.vector_store.search(query=q,top_k=k,filter=self._f(s))
    def _flt(self,items,c):
        if not settings.RAG_ENABLE_CONSTRAINT_FILTER:return items
        out=[]
        for it in items:
            m=dict(it.get("metadata",{}) or {});b=0.0;p=0.0;sg={}
            city=c.get("city");mc=self._mv(m,["city","destination","dest"])
            if city and mc and city not in str(mc): continue
            if city and mc and city in str(mc): b+=0.2;sg["city_match_score"]=0.2
            d=c.get("days");md=self._iv(self._mv(m,["days","trip_days","duration_days"]))
            if d and md is not None:
                diff=abs(md-d)
                if diff==0: b+=0.12;sg["days_match_score"]=0.12
                elif diff>=2: p+=0.08;sg["days_match_score"]=-0.08
            bg=c.get("budget_max");mb=self._iv(self._mv(m,["budget","budget_max","price","cost"]))
            if bg and mb is not None:
                if mb<=bg: b+=0.12;sg["budget_match_score"]=0.12
                else: p+=0.12;sg["budget_match_score"]=-0.12
            pe=c.get("persona");mp=self._mv(m,["persona","user_type","crowd"])
            if pe and mp:
                if pe in str(mp): b+=0.08;sg["persona_match_score"]=0.08
                else: p+=0.04;sg["persona_match_score"]=-0.04
            se=c.get("season");ms=self._mv(m,["season","month"])
            if se and ms:
                if se in str(ms): b+=0.05;sg["season_match_score"]=0.05
                else: p+=0.02;sg["season_match_score"]=-0.02
            it["constraint_bonus"]=b;it["constraint_penalty"]=p;it["rerank_signals"]=sg;out.append(it)
        return out
    def _rerank(self,items,q,c):
        if not settings.RAG_ENABLE_RERANK:return items
        city,pe=c.get("city"),c.get("persona")
        for it in items:
            t=self._n(it.get("title",""));x=self._n(it.get("content",""));b=it.get("constraint_bonus",0.0);p=it.get("constraint_penalty",0.0);sg=dict(it.get("rerank_signals",{}))
            if it.get("rewrite_query") and it.get("rewrite_query")!=q: b+=0.03;sg["rewrite_hit_score"]=0.03
            if city and city in t: b+=0.05;sg["title_hit_score"]=sg.get("title_hit_score",0.0)+0.05
            if pe and pe in x: b+=0.04;sg["content_hit_score"]=sg.get("content_hit_score",0.0)+0.04
            fs=it.get("hybrid_score",0.0)+b-p
            it["final_score"]=fs
            it["metadata"]={**it.get("metadata",{}),"vector_score":round(it.get("vector_score",0.0),6),"keyword_score":round(it.get("keyword_score",0.0),6),"hybrid_score":round(it.get("hybrid_score",0.0),6),"final_score":round(fs,6),"retrieval_type":it.get("retrieval_type","hybrid"),"rewrite_query":it.get("rewrite_query",q),"constraints":c,"rerank_signals":sg}
        items.sort(key=lambda i:i.get("final_score",i.get("hybrid_score",0.0)),reverse=True)
        return items
    async def retrieve(self,query:str,top_k:int=None,sources:Optional[List[str]]=None)->List[SearchResult]:
        top_k=top_k or settings.RAG_TOP_K;c=self._cons(query);qs=self._rw(query,c);ik=max(top_k*settings.RAG_RETRIEVAL_EXPAND_FACTOR,settings.RAG_KEYWORD_TOP_K,settings.RAG_TOP_K);allc={}
        for rq in qs:
            vr=await self._vr(rq,ik,sources);kr=[] if not settings.RAG_ENABLE_HYBRID else self.keyword_retriever.search(rq,ik,sources)
            for it in self._merge(vr,kr,rq):
                k=self._k(it.get("content",""),it.get("title",""),it.get("metadata",{}),it.get("metadata",{}).get("chunk_id",""))
                if k not in allc or it.get("hybrid_score",0.0)>allc[k].get("hybrid_score",0.0): allc[k]=it
        items=self._rerank(self._flt(list(allc.values()),c),query,c)
        res=[SearchResult(i.get("content",""),i.get("source","未知"),i.get("title",""),i.get("distance",0.0),i.get("metadata",{})) for i in items[:top_k]]
        logger.info(f"增强检索完成: query={query[:20]}..., rewrite={len(qs)}, candidates={len(items)}, results={len(res)}")
        return res
    async def retrieve_xiaohongshu(self,query:str,top_k:int=None)->List[SearchResult]: return await self.retrieve(query,top_k,sources=["小红书"])
    async def retrieve_web(self,query:str,top_k:int=None)->List[SearchResult]: return await self.retrieve(query,top_k,sources=["全网"])
    def get_knowledge_stats(self)->Dict[str,Any]:
        try:
            c=self.vector_store.get_collection_info();return {"collection_name":c.get("name"),"document_count":c.get("count",0),"persist_dir":c.get("persist_dir"),"chunk_size":settings.RAG_CHUNK_SIZE,"chunk_overlap":settings.RAG_CHUNK_OVERLAP}
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}");return {}

_retriever: Optional[Retriever]=None

def get_retriever()->Retriever:
    global _retriever
    if _retriever is None:_retriever=Retriever()
    return _retriever
