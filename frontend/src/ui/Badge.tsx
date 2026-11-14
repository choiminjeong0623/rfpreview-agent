// 상태 배지 (목업 .st.c-*). 색은 뜻으로 고른다: red 문제, orange 확인 필요, blue 정보·진행, green 끝남·준수, grey 그 밖.
export type Tone = 'red' | 'orange' | 'blue' | 'green' | 'grey'

const CLASS: Record<Tone, string> = { red: 'c-red', orange: 'c-ora', blue: 'c-blue', green: 'c-green', grey: 'c-grey' }

export function Badge({ tone, children, title }: { tone: Tone; children: React.ReactNode; title?: string }) {
  return <span className={`st ${CLASS[tone]}`} title={title}>{children}</span>
}
