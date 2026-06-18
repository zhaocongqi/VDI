package main

import (
	"context"
	"log"
	"os"

	"github.com/urfave/cli/v3"
	"vdi-installer/pkg/console"
	"vdi-installer/pkg/version"
)

func main() {
	cmd := &cli.Command{
		Name:    "vdi-installer",
		Version: version.FriendlyVersion(),
		Usage:   "Console application to install VDI platform",
		Action: func(context.Context, *cli.Command) error {
			return console.RunConsole()
		},
	}
	if err := cmd.Run(context.Background(), os.Args); err != nil {
		log.Fatalf("Error: %v", err)
	}
}
