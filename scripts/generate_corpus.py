#!/usr/bin/env python3
"""Generate a large, explicitly labeled structured seed corpus for ARBITER Biology.

The generated rows are not claimed to be ScienCell catalog records or experimental facts.
They are normalized biological, operational, and commercial decision objects designed to
exercise the local 72D field before private/customer data and real catalogs are ingested.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

CELLS = [
    'human cortical neuron','human dopaminergic neuron','human GABAergic neuron','human motor neuron','human sensory neuron',
    'human neural stem cell','human astrocyte','human microglia','human oligodendrocyte precursor','human brain microvascular endothelial cell',
    'human cardiomyocyte','human hepatocyte','human renal proximal tubule cell','human lung epithelial cell','human fibroblast',
    'human endothelial cell','human mesenchymal stem cell','human pluripotent stem cell','human skeletal muscle cell','human pancreatic beta cell',
    'human T cell','human B cell','human macrophage','human monocyte','human dendritic cell','human intestinal epithelial cell',
    'human keratinocyte','human chondrocyte','human osteoblast','human adipocyte','patient-derived organoid','tumor spheroid'
]
PATHWAYS = [
    'Wnt beta-catenin','NF-kB inflammatory','hypoxia HIF','cAMP CREB','MAPK AP-1','p53 DNA-damage','PI3K AKT mTOR',
    'JAK STAT','TGF-beta SMAD','Notch','Hedgehog','Nrf2 oxidative stress','integrated stress response','unfolded protein response',
    'mitochondrial apoptosis','autophagy lysosome','innate immune cGAS STING','interferon response','calcium signaling','synaptic plasticity',
    'cell-cycle checkpoint','senescence SASP','ferroptosis','pyroptosis','neurotrophin signaling','DNA repair','epithelial mesenchymal transition'
]
PERTURBATIONS = [
    'small-molecule treatment','cytokine challenge','oxidative stress','hypoxia exposure','nutrient deprivation','CRISPR knockout',
    'CRISPR activation','siRNA knockdown','protein supplementation','growth-factor withdrawal','mechanical stress','temperature excursion',
    'viral transduction','dose response','time-course treatment','patient-serum exposure','co-culture interaction','drug combination',
    'genotoxic challenge','inflammatory stimulation','metabolic inhibition','recovery after washout'
]
READOUTS = [
    'cell viability','cell identity','differentiation state','pathway reporter activity','qPCR gene-expression profile','bulk RNA-seq signature',
    'single-cell RNA-seq state','spatial transcriptomic pattern','proteomic abundance','phosphoproteomic activity','metabolomic profile',
    'high-content imaging phenotype','electron microscopy ultrastructure','neurite morphology','mitochondrial morphology','organoid architecture',
    'secreted cytokine profile','electrophysiology','barrier permeability','cell migration','apoptosis kinetics','cell-cycle distribution',
    'target engagement','compound potency','batch reproducibility','lot-to-lot drift'
]
DISEASES = [
    'Alzheimer disease','Parkinson disease','amyotrophic lateral sclerosis','multiple sclerosis','neuropathic pain','ischemic injury',
    'glioblastoma','breast cancer','colorectal cancer','non-small-cell lung cancer','fibrosis','nonalcoholic steatohepatitis',
    'type 2 diabetes','cardiomyopathy','kidney injury','inflammatory bowel disease','rheumatoid arthritis','systemic lupus erythematosus',
    'viral infection','bacterial sepsis','rare genetic disease','developmental disorder','age-related degeneration','drug-induced toxicity'
]
OMICS = [
    'whole-genome sequencing','whole-exome sequencing','targeted sequencing','bulk RNA sequencing','single-cell RNA sequencing',
    'single-nucleus RNA sequencing','spatial transcriptomics','ATAC-seq','ChIP-seq','DNA methylation profiling','long-read sequencing',
    'proteomics','phosphoproteomics','metabolomics','lipidomics','secretomics','CRISPR screen','cell-free DNA','copy-number profiling'
]
IMAGING = [
    'confocal microscopy','high-content fluorescence imaging','electron microscopy','whole-slide pathology','live-cell imaging',
    'super-resolution microscopy','spatial imaging','organoid imaging','brightfield morphology','multiplex immunofluorescence',
    'flow cytometry imaging','neurite tracing','mitochondrial network imaging','3D tissue reconstruction','cell neighborhood mapping'
]
OPS_EVENTS = [
    'missed carrier pickup','dry-ice depletion risk','temperature logger excursion','wrong product picked','inventory shortage','lot release delay',
    'vendor backorder','instrument failure','reagent shortage','customer receiving-window conflict','customs hold','damaged package',
    'sample identity discrepancy','quality-control failure','protocol deviation','operator capacity constraint','priority-order conflict',
    'forecast variance','cold-room alarm','database synchronization failure','customer complaint','recurring shipment delay',
    'expired material','supplier quality issue','documentation gap'
]
OPS_ACTIONS = [
    'same-day recovery','validated repack','alternate inventory allocation','priority reschedule','quality hold','customer notification',
    'carrier escalation','vendor substitution','root-cause review','corrective action','preventive action','lot quarantine','replacement shipment',
    'extended stability assessment','schedule resequencing','budget reallocation','staff reassignment','instrument reroute','controlled disposal',
    'regulatory documentation','management escalation','service credit','process redesign','supplier qualification','data reconciliation'
]
BUSINESS_LINES = [
    'experiment-to-product matching','GeneQuery interpretation','phenotype search','multi-omics interpretation','patient-to-model matching',
    'private biological data workspace','laboratory decision infrastructure','biological field API','on-premise biology appliance',
    'research capability marketplace','translational program intelligence','scientific catalog intelligence','quality and CAPA intelligence',
    'cold-chain decision platform','biological asset indexing','drug-discovery model selection','cell identity certification',
    'regional La Jolla biological intelligence network'
]
CUSTOMERS = ['biotechnology company','pharmaceutical company','CRO','academic laboratory','sequencing company','diagnostics company','hospital research program','cell therapy company','instrument company','biobank']

DOMAINS = ('experiment','genequery','omics','imaging','operations','atlas','translation','portfolio')

def stable_id(prefix: str, *parts: str) -> str:
    raw='|'.join(parts).encode()
    return prefix+':'+hashlib.sha1(raw).hexdigest()[:18]

def emit(out, obj):
    out.write(json.dumps(obj,ensure_ascii=False,separators=(',',':'))+'\n')

def row(domain, category, title, text, source='ARBITER structured biology seed', tags=(), **meta):
    rid=stable_id(domain,category,title,text)
    return {
        'id':rid,'code':rid.split(':')[1][:10].upper(),'title':title,'name':title,'text':text,
        'object_type':category,'category':category,'domain':domain,'mode':domain,'source':source,'source_url':'',
        'tenant':'public','tags':list(tags),'metadata':{'generated_seed':True,**meta}
    }

def generate(path: Path, target: int) -> int:
    path.parent.mkdir(parents=True,exist_ok=True)
    n=0
    with path.open('w',encoding='utf-8') as out:
        # Experimental packages and components
        for i in range(min(target,2800)):
            cell=CELLS[i%len(CELLS)]; pathway=PATHWAYS[(i*5+3)%len(PATHWAYS)]; perturb=PERTURBATIONS[(i*7+2)%len(PERTURBATIONS)]
            readout=READOUTS[(i*11+1)%len(READOUTS)]; disease=DISEASES[(i*13+4)%len(DISEASES)]
            title=f'{cell.title()} · {pathway} experimental package'
            text=(f'Experimental configuration using {cell} to study {disease} under {perturb}; measure {pathway} activity with {readout}, '
                  'include matched negative and positive controls, compatible culture conditions, identity confirmation, viability, dose and time-course design, reproducibility checks, and a ranked next experiment.')
            emit(out,row('experiment','Experimental Package',title,text,tags=(cell,pathway,disease,readout)));n+=1
            if n>=target:return n
        # Interpretation states
        for i in range(2500):
            cell=CELLS[(i*3)%len(CELLS)]; pathway=PATHWAYS[(i*7)%len(PATHWAYS)]; r1=READOUTS[(i*5)%len(READOUTS)]; r2=READOUTS[(i*9+2)%len(READOUTS)]
            title=f'{pathway} state in {cell}'
            text=(f'Interpret a combined {r1} and {r2} pattern in {cell} as evidence for {pathway}; rank cell identity, cell state, mechanism, '
                  'confounders, batch effects, orthogonal validation, relevant reporter vector or qPCR panel, and the most coherent next measurement.')
            emit(out,row('genequery','Biological Interpretation',title,text,tags=(cell,pathway,r1,r2)));n+=1
            if n>=target:return n
        # Omics integration
        for i in range(2200):
            o1=OMICS[i%len(OMICS)];o2=OMICS[(i*5+1)%len(OMICS)];disease=DISEASES[(i*7)%len(DISEASES)];pathway=PATHWAYS[(i*11)%len(PATHWAYS)];cell=CELLS[(i*13)%len(CELLS)]
            title=f'{o1.title()} + {o2} integration for {disease}'
            text=(f'Integrate {o1} with {o2} in {cell} to resolve {disease}; rank variants, genes, proteins, pathways, cell states, causal hypotheses, '
                  f'and validation experiments with emphasis on {pathway}, cohort stratification, reproducibility, and actionable evidence gaps.')
            emit(out,row('omics','Multi-Omics Object',title,text,tags=(o1,o2,disease,pathway)));n+=1
            if n>=target:return n
        # Imaging/phenomics
        for i in range(1700):
            img=IMAGING[i%len(IMAGING)]; cell=CELLS[(i*5)%len(CELLS)]; pathway=PATHWAYS[(i*9)%len(PATHWAYS)]; readout=READOUTS[(i*13)%len(READOUTS)]
            title=f'{img.title()} phenotype · {cell}'
            text=(f'Biological image object from {img} of {cell}; encode morphology, subcellular organization, treatment response, {readout}, '
                  f'and coherence with {pathway}. Support similarity retrieval, anomaly detection, batch drift, nearest experiments, linked omics, protocols, lots, and outcomes.')
            emit(out,row('imaging','Imaging Phenotype',title,text,tags=(img,cell,pathway,readout)));n+=1
            if n>=target:return n
        # Operations
        for i in range(1700):
            event=OPS_EVENTS[i%len(OPS_EVENTS)]; action=OPS_ACTIONS[(i*7)%len(OPS_ACTIONS)]; customer=CUSTOMERS[(i*11)%len(CUSTOMERS)]
            title=f'{action.title()} for {event}'
            text=(f'Operational action for a {event} affecting a {customer}; evaluate product stability, sample integrity, inventory scarcity, deadline, customer impact, '
                  f'cost, vendor performance, ISO documentation, root cause, corrective action, and whether {action} is the highest-coherence response.')
            emit(out,row('operations','Operational Action',title,text,tags=(event,action,customer)));n+=1
            if n>=target:return n
        # 72D atlas assets
        for i in range(900):
            cell=CELLS[(i*2)%len(CELLS)]; r=READOUTS[(i*5)%len(READOUTS)]; o=OMICS[(i*7)%len(OMICS)]; img=IMAGING[(i*11)%len(IMAGING)]
            title=f'72D biological asset · {cell} · {r}'
            text=(f'Cross-modal biological asset linking {cell}, {r}, {o}, {img}, protocol, reagent lot, operator, instrument, treatment, phenotype, and outcome. '
                  'Use as a compact searchable 72D operational signature while retaining the original raw files in archival storage.')
            emit(out,row('atlas','72D Biological Asset',title,text,tags=(cell,r,o,img)));n+=1
            if n>=target:return n
        # Translation
        for i in range(900):
            disease=DISEASES[i%len(DISEASES)]; pathway=PATHWAYS[(i*7)%len(PATHWAYS)]; cell=CELLS[(i*11)%len(CELLS)]; readout=READOUTS[(i*13)%len(READOUTS)]
            title=f'Patient-to-model match · {disease} · {pathway}'
            text=(f'Translational matching object connecting a patient or cohort profile for {disease} to {cell}, {pathway}, {readout}, biomarkers, target hypotheses, '
                  'assay feasibility, model fidelity, safety, clinical evidence, responder definition, and the strongest validation program.')
            emit(out,row('translation','Translational Match',title,text,tags=(disease,pathway,cell,readout)));n+=1
            if n>=target:return n
        # Portfolio
        for i in range(700):
            line=BUSINESS_LINES[i%len(BUSINESS_LINES)]; customer=CUSTOMERS[(i*5)%len(CUSTOMERS)]; pathway=PATHWAYS[(i*7)%len(PATHWAYS)]
            title=f'{line.title()} for {customer}'
            text=(f'Commercial product-line object for {line} serving a {customer}; rank strategic fit, proprietary data advantage, biological meaning, {pathway} relevance, '
                  'implementation cost, licensing model, recurring revenue, La Jolla corridor network effects, defensibility, and time to validated value.')
            emit(out,row('portfolio','Commercial Opportunity',title,text,tags=(line,customer,pathway)));n+=1
            if n>=target:return n
    return n

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',default='corpus/structured_seed.jsonl');ap.add_argument('--count',type=int,default=12000)
    args=ap.parse_args(); path=Path(args.output); n=generate(path,args.count); print(f'generated {n:,} structured seed objects -> {path}')
if __name__=='__main__':main()
