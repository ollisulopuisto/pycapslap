import { ElectronAPI } from '@electron-toolkit/preload'
import type api from './api'

declare global {
  interface Window {
    electron: ElectronAPI
    api: typeof api
    rust: {
      openFiles: (filters?: any) => Promise<string[] | null>
      filesExist: (paths: string[]) => Promise<boolean[]>
      call: (method: string, params: any, requestId?: string) => Promise<any>
      onProgress: (cb: (p: any) => void) => () => void
      getFilePath: (file: File) => string | null
      installOrukeet: () => Promise<{ ready: boolean }>
      checkOrukeetInstalled: () => Promise<boolean>
    }
  }
}
