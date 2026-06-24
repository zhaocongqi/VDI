// +build !darwin

package termbox

// 开启 ESC 等待：收到 ESC 字节后短暂等待（esc_wait_delay，默认 100ms）后续字节，
// 用于区分"方向键等转义序列的 ESC 前缀"与"用户单按 ESC 键"。
//
// 背景：Linux 控制台/串口/VMware 控制台下，方向键转义序列（如 ESC [ A）的字节
// 可能分批到达（SIGIO 逐批通知）。若不等待，单独到达的 ESC 前缀会被立即判为
// KeyEsc，触发 TUI 面板的 ESC 回退逻辑——表现为密码面板误回退（密码看似没输入
// 进去）、网卡面板误回退（输入框串行）。
//
// 开启等待后：分批到达的方向键在 esc_wait_delay 内凑齐 → 正确解析为方向键；
// 单按 ESC → 超时后产生 KeyEsc，回退功能保留（代价是 100ms 延迟，与 macOS 一致）。
//
// See https://github.com/nsf/termbox-go/issues/132
func enable_wait_for_escape_sequence() bool {
	return true
}
