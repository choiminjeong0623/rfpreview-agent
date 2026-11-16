// 정렬 비교 함수. 기본 sort()와 같은 순서(UTF-16 코드 단위)를 비교 함수로 적는다.
// localeCompare는 한글·대소문자 순서가 달라 화면 순서가 바뀌므로 쓰지 않는다.

/** 문자열을 기본 sort()와 같은 순서로 */
export const byCodeUnit = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0)
