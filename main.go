package main

import (
	"context"
	"log"
	"os"

	"github.com/urfave/cli/v3"
	"vdi-installer/pkg/config"
	"vdi-installer/pkg/console"
	"vdi-installer/pkg/version"
)

func main() {
	cmd := &cli.Command{
		Name:    "vdi-installer",
		Version: version.FriendlyVersion(),
		Usage:   "Console application to install VDI platform",
		Flags: []cli.Flag{
			&cli.BoolFlag{
				Name:  "auto-install",
				Usage: "Render kickstart ks.cfg from default config and exit (no TUI, for automated testing / build-time ks generation)",
			},
			&cli.StringFlag{
				Name:  "ks-out",
				Usage: "Path to write rendered kickstart (used with --auto-install, default /tmp/ks-rendered.cfg)",
			},
		},
		Action: func(ctx context.Context, c *cli.Command) error {
			if c.Bool("auto-install") {
				return console.AutoInstall(c.String("ks-out"))
			}
			return console.RunConsole()
		},
	}
	if err := cmd.Run(context.Background(), os.Args); err != nil {
		log.Fatalf("Error: %v", err)
	}
}

// Ensure config package is used (for ldflags injection)
var _ = config.RoleFirst
