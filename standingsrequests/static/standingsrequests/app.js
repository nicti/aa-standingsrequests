var standingsApp = angular.module('standingsApp', ['ui.bootstrap']);

standingsApp.config(['$httpProvider', function ($httpProvider) {
    // Enable CSRF tokens from Django
    $httpProvider.defaults.xsrfCookieName = 'csrftoken';
    $httpProvider.defaults.xsrfHeaderName = 'X-CSRFToken';
}]);

// Components
function StandingsIconController($scope) {
    $scope.getAbsStanding = function (std) {
        if (std < -5.0) {
            return -10;
        } else if (std < 0.0) {
            return -5;
        } else if (std == 0.0) {
            return 0;
        } else if (std <= 5.0) {
            return 5;
        } else if (std <= 10.0) {
            return 10;
        } else return undefined;
    }

    this.$onInit = function () {
        $scope.standingIcon = $scope.getAbsStanding(this.standing);
        $scope.standing = this.standing;
    };
};


standingsApp.component('standingsIcon', {
    templateUrl: urls.standings_icon_template,
    bindings: {
        standing: '<',
    },
    controller: StandingsIconController
});

standingsApp.component('clipboardCopy', {
    templateUrl: urls.copy_field_template,
    bindings: {
        copy: '<',
    },
    controller: function ($scope, $interval) {
        $scope.onCopy = function () {
            var target = document.getElementById($scope.id);
            target.select();
            document.execCommand("copy");

            // Deselect
            if (document.selection) {
                document.selection.empty();
            } else if (window.getSelection) {
                window.getSelection().removeAllRanges();
            }

            // Flash icon green
            $scope.style = { 'color': '#0BBF2C' };
            $interval(function () {
                $scope.style = {};
            }, 1000, 1)
        };

        this.$onInit = function () {
            $scope.copy = this.copy;
            $scope.style = {};
            $scope.id = $scope.randomString(16);
        };

        $scope.randomString = function (length) {
            return Math.round((Math.pow(36, length + 1) - Math.random() * Math.pow(36, length))).toString(36).slice(1);
        }
    }
});

standingsApp.component('boolCheckmark', {
    templateUrl: urls.bool_tick_template,
    bindings: {
        value: '<',
        trueTitle: '@',
        falseTitle: '@',

    },
    controller: function ($scope) {
        this.$onInit = function () {
            $scope.value = this.value;
            $scope.trueTitle = this.trueTitle;
            $scope.falseTitle = this.falseTitle;
        };
    }
});
