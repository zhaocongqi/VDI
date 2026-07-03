package main

import (
	"context"
	"log"
	"os"

	"github.com/urfave/cli/v3"
	"vdi-installer/pkg/version"
)

func main() {
	cmd := &cli.Command{
		Name:    "vdi-installer",
		Version: version.FriendlyVersion(),
		Usage:   "VDI Installer CLI (TUI deprecated in favor of PyAnaconda Addon)",
		Action: func(ctx context.Context, c *cli.Command) error {
			println("VDI Installer is running in backend daemon mode.")
			println("The TUI console has been deprecated. Please use PyAnaconda GUI instead.")
			return nil
		},
	}
	if err := cmd.Run(context.Background(), os.Args); err != nil {
		log.Fatalf("Error: %v", err)
	}
}
