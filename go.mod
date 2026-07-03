module vdi-installer

go 1.26

require (
	github.com/imdario/mergo v0.3.16
	github.com/rancher/mapper v0.0.0-20190814232720-058a8b7feb99
	github.com/sirupsen/logrus v1.9.3
	github.com/stretchr/testify v1.10.0
	github.com/tredoe/osutil v1.5.0
	github.com/urfave/cli/v3 v3.4.1
	gopkg.in/yaml.v3 v3.0.1
	k8s.io/apimachinery v0.32.6
)

require (
	github.com/davecgh/go-spew v1.1.2-0.20180830191138-d8f796af33cc // indirect
	github.com/docker/go-units v0.5.0 // indirect
	github.com/ghodss/yaml v1.0.0 // indirect
	github.com/mattn/go-shellwords v1.0.10 // indirect
	github.com/pmezard/go-difflib v1.0.1-0.20181226105442-5d4384ee4fb2 // indirect
	github.com/rancher/wrangler v0.0.0-20190426050201-5946f0eaed19 // indirect
	golang.org/x/sys v0.28.0 // indirect
	gopkg.in/yaml.v2 v2.4.0 // indirect
	k8s.io/utils v0.0.0-20241104100929-3ea5e8cea738 // indirect
)

replace (
	github.com/nsf/termbox-go => ./third_party/termbox-go
	github.com/rancher/wrangler => github.com/rancher/wrangler v1.1.1
	k8s.io/api => k8s.io/api v0.32.6
	k8s.io/apimachinery => k8s.io/apimachinery v0.32.6
	k8s.io/client-go => k8s.io/client-go v0.32.6
	k8s.io/kubelet => k8s.io/kubelet v0.32.6
)
