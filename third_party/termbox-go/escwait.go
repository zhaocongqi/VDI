// +build !darwin

package termbox

// 保持与上游 termbox 一致：Linux 关闭 ESC 等待（与 harvester-installer 相同配置）。
//
// 曾尝试开启 esc_wait（return true）以解决方向键转义序列分批到达时 ESC 前缀
// 被误判为 KeyEsc 的问题，但 esc_wait 的 100ms 阻塞在用户快速连按方向键时导致
// 按键积压、面板切换显示错乱，弊大于利。harvester 生产环境长期使用 escwait=false
// + InputEsc=true，主流终端方向键一次性到达不会误判。
//
// TUI 串行/叠加的真正根因不在 termbox（与 harvester 零 diff），而在 getty 多实例
// （console=tty0 导致多个 vdi-installer 争用键盘），已在安装器启动层修复。
//
// See https://github.com/nsf/termbox-go/issues/132
func enable_wait_for_escape_sequence() bool {
	return false
}
