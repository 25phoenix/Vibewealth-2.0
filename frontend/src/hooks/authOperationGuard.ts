/** Invalidates async auth completions without cancelling shared HTTP requests. */
export class AuthOperationGuard {
  private generation = 0
  private active = false

  activate(): void {
    this.active = true
  }

  begin(): number {
    this.generation += 1
    return this.generation
  }

  invalidate(): void {
    this.active = false
    this.generation += 1
  }

  isCurrent(generation: number): boolean {
    return this.active && generation === this.generation
  }
}
