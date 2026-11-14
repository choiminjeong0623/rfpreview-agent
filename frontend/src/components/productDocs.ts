// 제품표 상세 "문서" 탭: LS ELECTRIC 공식 자료실의 카탈로그·매뉴얼·시험 성적서·인증서 (change add-product-docs, SCR-16).
// productDocs.json은 scripts/fetch-product-docs.py가 공식 자료실 API에서 만든다. 파일은 받지 않고 공식 내려받기 주소만 둔다.
// 문서는 제품 계열 공통 자료다. 이 모델에 해당하는지는 문서에서 확인한다.
import data from './productDocs.json'
import { productPhoto } from './productPhotos'

export type DocKind = 'catalog' | 'manual' | 'test' | 'cert'
export type ProductDoc = { kind: DocKind; title: string; date: string; lang: string; org: string | null; url: string }
export type ProductDocs = { page: string; docs: ProductDoc[]; retrieved: string }

export const DOC_KINDS: [DocKind, string][] = [['catalog', '카탈로그'], ['manual', '매뉴얼'], ['test', '시험 성적서'], ['cert', '인증서']]

const FAMILIES = data.families as Record<string, { page: string; docs: ProductDoc[] }>

/** 제품표 source_doc의 카탈로그 번호로 그 계열 문서 묶음을 찾는다. 없으면 null. */
export function productDocs(sourceDoc: string | null | undefined): ProductDocs | null {
  const ph = productPhoto(sourceDoc)
  const f = ph ? FAMILIES[ph.docs] : undefined
  return f ? { ...f, retrieved: data.retrieved } : null
}

/** 제품표 값의 출처 카탈로그(예: CAT-C05001-26)와 같은 번호의 카탈로그 파일인지 */
export function isSourceCatalog(doc: ProductDoc, sourceDoc: string | null | undefined): boolean {
  const m = sourceDoc?.match(/CAT-(C[0-9A-Z]+-\d+)/)
  return doc.kind === 'catalog' && !!m && doc.url.includes(m[1])
}
