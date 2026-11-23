import { describe, expect, it } from 'vitest'
import { productDocs } from './productDocs'

// 제품표 상세 "문서" 탭 (add-product-docs): 사진 파일이 없는 공개본에서도 카탈로그 번호로 문서 묶음을 찾는다
describe('productDocs', () => {
  it('카탈로그 번호로 계열 문서 묶음', () => {
    expect(productDocs('CAT-C81001-08 p.19')?.docs.some((d) => d.title.includes('[GIS] Total Solution'))).toBe(true)
    expect(productDocs('CAT-C80081-01')?.docs.some((d) => d.title.includes('[GSH-20V]_국문'))).toBe(true)
  })

  it('모르는 카탈로그나 출처가 없으면 null', () => {
    expect(productDocs('CAT-C99999-01')).toBeNull()
    expect(productDocs(null)).toBeNull()
  })
})
