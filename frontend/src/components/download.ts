/** 받은 파일을 브라우저에 저장한다 (내려받기 공용). */
export function saveFile(name: string, blob: Blob) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)       // 문서에 붙여야 브라우저가 파일 이름을 쓴다
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
