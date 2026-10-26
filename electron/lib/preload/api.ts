import { ipcRenderer, webUtils } from 'electron'

const api = {
  send: (channel: string, ...args: any[]) => {
    ipcRenderer.send(channel, ...args)
  },
  receive: (channel: string, func: (...args: any[]) => void) => {
    ipcRenderer.on(channel, (_, ...args) => func(...args))
  },
  invoke: (channel: string, ...args: any[]) => {
    return ipcRenderer.invoke(channel, ...args)
  },
  removeAllListeners: (channel: string) => {
    ipcRenderer.removeAllListeners(channel)
  },
}

const rust = {
  openFiles: (filters?: any) => ipcRenderer.invoke('dialog:openFiles', { filters }),
  filesExist: (paths: string[]): Promise<boolean[]> => ipcRenderer.invoke('files:exist', paths),
  call: (method: string, params: any, requestId?: string) =>
    ipcRenderer.invoke('core:call', { method, params, requestId }),
  onProgress: (cb: (p: any) => void) => {
    const listener = (_: any, msg: any) => cb(msg)
    ipcRenderer.on('core:progress', listener)
    return () => ipcRenderer.removeListener('core:progress', listener)
  },
  getFilePath: (file: File) => {
    try {
      return webUtils.getPathForFile(file)
    } catch (error) {
      return null
    }
  },
  installOrukeet: () => {
    return ipcRenderer.invoke('core:call', {
      method: 'installOrukeet',
      params: {},
    })
  },
  checkOrukeetInstalled: () => {
    return ipcRenderer.invoke('core:call', {
      method: 'checkOrukeetInstalled',
      params: {},
    })
  },
}

export default api
export { rust }
