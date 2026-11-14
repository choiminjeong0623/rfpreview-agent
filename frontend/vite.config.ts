import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 개발 중에는 /api 요청을 백엔드(기본 8000번)로 넘긴다.
const apiTarget = process.env.VITE_API_TARGET ?? 'http://localhost:8000'
// Docker(윈도우·맥)에서는 폴더를 붙여도 파일 바뀜 알림이 컨테이너로 오지 않아 화면이 옛 코드로 남는다.
// VITE_USE_POLLING=1이면 주기적으로 파일을 직접 확인한다 (docker-compose.yml에서 켬).
const usePolling = process.env.VITE_USE_POLLING === '1'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    proxy: { '/api': apiTarget },
    watch: usePolling ? { usePolling: true, interval: 300 } : undefined,
  },
})
