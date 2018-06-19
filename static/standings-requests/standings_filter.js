// Provides data binding for the filterStandings
standingsApp.service('FilterStandingsService',  function(){
    var fac = {};
    fac.standing = {};
    fac.standing.from = -10;
    fac.standing.to = 10;
    fac.has_scopes = null;
    fac.search = "";
    fac.searchLabel = "";
    fac.searchState = "";
    return fac;
});

// Provides filtering for standings pilot/corp/alliance
standingsApp.filter('filterStandings', ['FilterStandingsService', function(FilterStandingsService){
    return function( items ) {
        var out = [];
        var svc = FilterStandingsService;

        angular.forEach(items, function(item) {
            // Looping through each filter item
            // If it doesn't meet a search criteria we return early
            // and the item never gets added to the function output.
            if (svc.standing.from > item.standing || svc.standing.to < item.standing) {
                // Standing not in range
                return;
            }

            if (svc.has_scopes === true && item.has_required_scopes === false) {
                return;
            } else if (svc.has_scopes === false && item.has_required_scopes === true) {
                return;
            }
            
            if (svc.searchState.length > 0) {
                if (! item.state.includes(svc.searchState)){
                    return;
                }
            }

            // Text search
            if (svc.search.length > 0) {
                var content = (
                    (item.character_name ? item.character_name : "") +
                    (item.corporation_name ? item.corporation_name : "") +
                    (item.corporation_ticker ? item.corporation_ticker : "") +
                    (item.alliance_name ? item.alliance_name : "") +
                    (item.main_character_name ? item.main_character_name : "") +
                    (item.main_character_ticker ? item.main_character_ticker : "")
                    ).toLowerCase();

                if (content.indexOf(svc.search.toLowerCase()) === -1) {
                    return;
                }
            }
            // Label search
            if (svc.searchLabel.length > 0) {
                if (!item.labels || !item.labels.length ||
                    item.labels.join(' ').toLowerCase().indexOf(svc.searchLabel.toLowerCase()) === -1) {
                    return;
                }
            }

            out.push(item);
        });
        return out;
    };
}]);

standingsApp.component('standingsFilterControls', {
    templateUrl: urls.standings_filter_controls_template,
    bindings: {
        scopes: '<',
        states: '<',
    },
    controller: function StandingsFilterControls ($scope, FilterStandingsService) {
        this.$onInit = function () {
            $scope.filters = FilterStandingsService;
            $scope.scopes = this.scopes !== undefined ? this.scopes : false;
            $scope.states = this.states !== undefined ? this.states : false;
        };
    },
});
