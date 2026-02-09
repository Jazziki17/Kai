/**
 * Python Bridge — Spawns and monitors the Kai API server.
 * Handles health checks, auto-restart, and graceful shutdown.
 */

import { ChildProcess, spawn } from 'child_process'
import { join } from 'path'
import http from 'http'

const PORT = 8420
const HEALTH_URL = `http://localhost:${PORT}/api/status`
const HEALTH_INTERVAL = 5000
const MAX_RESTARTS = 5
const STARTUP_TIMEOUT = 15000

export class PythonBridge {
  private process: ChildProcess | null = null
  private healthTimer: NodeJS.Timeout | null = null
  private restartCount = 0
  private stopping = false

  private externalServer = false

  async start(): Promise<void> {
    this.stopping = false

    // Check if server is already running (started externally)
    const alreadyUp = await this.healthCheck()
    if (alreadyUp) {
      console.log('[PythonBridge] Server already running — attaching to existing instance')
      this.externalServer = true
      this.startHealthCheck()
      return
    }

    this.spawn()
    await this.waitForReady()
    this.startHealthCheck()
  }

  async stop(): Promise<void> {
    this.stopping = true
    this.stopHealthCheck()

    if (this.externalServer) {
      // Don't kill an externally managed server
      return
    }

    if (this.process) {
      this.process.kill('SIGTERM')

      // Wait up to 5s for graceful shutdown
      await new Promise<void>((resolve) => {
        const timeout = setTimeout(() => {
          if (this.process) {
            this.process.kill('SIGKILL')
          }
          resolve()
        }, 5000)

        if (this.process) {
          this.process.on('exit', () => {
            clearTimeout(timeout)
            resolve()
          })
        } else {
          clearTimeout(timeout)
          resolve()
        }
      })

      this.process = null
    }
  }

  async restart(): Promise<void> {
    await this.stop()
    this.stopping = false
    this.restartCount = 0
    await this.start()
  }

  get isRunning(): boolean {
    return this.process !== null && !this.process.killed
  }

  private spawn(): void {
    console.log('[PythonBridge] Starting python -m kai.api ...')

    // Find the project root (parent of desktop/)
    const projectRoot = join(__dirname, '..', '..', '..')

    this.process = spawn('python3', ['-m', 'kai.api'], {
      cwd: projectRoot,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env },
    })

    this.process.stdout?.on('data', (data: Buffer) => {
      console.log(`[Kai] ${data.toString().trim()}`)
    })

    this.process.stderr?.on('data', (data: Buffer) => {
      console.error(`[Kai:err] ${data.toString().trim()}`)
    })

    this.process.on('exit', (code) => {
      console.log(`[PythonBridge] Process exited with code ${code}`)
      this.process = null

      if (!this.stopping && this.restartCount < MAX_RESTARTS) {
        this.restartCount++
        console.log(`[PythonBridge] Auto-restarting (${this.restartCount}/${MAX_RESTARTS})...`)
        setTimeout(() => this.spawn(), 2000)
      }
    })
  }

  private waitForReady(): Promise<void> {
    return new Promise((resolve, reject) => {
      const startTime = Date.now()

      const check = () => {
        if (Date.now() - startTime > STARTUP_TIMEOUT) {
          reject(new Error('Python server failed to start within timeout'))
          return
        }

        this.healthCheck()
          .then((ok) => {
            if (ok) {
              console.log('[PythonBridge] Server is ready')
              resolve()
            } else {
              setTimeout(check, 500)
            }
          })
          .catch(() => setTimeout(check, 500))
      }

      setTimeout(check, 1000) // Give server a moment to start
    })
  }

  private healthCheck(): Promise<boolean> {
    return new Promise((resolve) => {
      http
        .get(HEALTH_URL, (res) => {
          resolve(res.statusCode === 200)
        })
        .on('error', () => {
          resolve(false)
        })
    })
  }

  private startHealthCheck(): void {
    this.healthTimer = setInterval(async () => {
      const ok = await this.healthCheck()
      if (!ok && !this.stopping) {
        console.warn('[PythonBridge] Health check failed, server may be down')
      }
    }, HEALTH_INTERVAL)
  }

  private stopHealthCheck(): void {
    if (this.healthTimer) {
      clearInterval(this.healthTimer)
      this.healthTimer = null
    }
  }
}
