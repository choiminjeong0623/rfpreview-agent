// 제품표 상세의 제품 사진 (change add-product-photos, SCR-16).
// 사진은 LS ELECTRIC 공식 사이트의 제품 계열 대표 사진이다. 모델마다 다른 사진이 아니다.
// 사용 허락: 2026-10-31 LS ELECTRIC 측에서 받음(팀 프로젝트용). 공개본에는 사진 파일을 넣지 않았다.
// 제품표 source_doc의 카탈로그 번호(CAT-Cxxxxx-xx)로 사진을 찾는다. 없으면 사진을 보이지 않는다.

export type ProductPhoto = {
  src: string        // public 아래 파일
  family: string     // 사진이 보여 주는 제품 계열
  page: string       // 사진이 실린 공식 페이지
  site: string       // 출처 사이트 이름
  docs: string       // 관련 문서 묶음 (productDocs.json families 키, add-product-docs)
}

// 공개 포트폴리오본: LS ELECTRIC 사진은 팀 프로젝트용으로 받은 사용 허락이라 저장소에서 뺐다.
// 사진이 없으면 화면은 사진 칸을 보이지 않는다 (아래 productPhoto가 null).
export const PRODUCT_PHOTOS: Record<string, ProductPhoto> = {}

/** 제품표 source_doc(예: "CAT-C05001-26 p.39, p.45")의 카탈로그 번호로 사진을 찾는다. */
export function productPhoto(sourceDoc: string | null | undefined): ProductPhoto | null {
  const m = sourceDoc?.match(/CAT-C[0-9A-Z]+-\d+/)
  return (m && PRODUCT_PHOTOS[m[0]]) || null
}
